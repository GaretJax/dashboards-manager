# Agent Operational Reporting and Diagnostic Screenshots Plan

Status: planned, not implemented.

## Goal

Have each kiosk agent periodically publish current host, browser, display,
playlist, power, and health state. Keep one latest diagnostic screenshot per
screen/content pair in Django. Screenshots stay in memory on agent and are
uploaded directly; no screenshot files are written locally.

Depends on the content/playlist split so every playlist item has stable
`content_id`. Also integrates with planned power state, dialog handling, and
content injection behavior.

## Backend runtime state

Add a one-to-one `ScreenRuntimeStatus` model rather than adding volatile fields
to `Screen`:

### Agent/host

- Screen identity through `Screen` foreign key.
- `agent_version`.
- `browser_version`.
- `agent_started_at` and `uptime_seconds`.
- server-owned `last_check_in` timestamp.
- `health_state`: `unknown`, `healthy`, `degraded`, or `error`.
- bounded `health_error` / latest error summary.
- load averages (1/5/15 minute, nullable).
- memory total, used, available bytes and percentage (nullable).

### Current screen state

- current content foreign key, nullable.
- `last_successful_page_load_at`.
- desired power state.
- actual power state, nullable/unknown when unavailable.
- display identity/output name.
- resolution width/height.
- refresh rate Hz.
- orientation/transform.
- browser error and display error, separately bounded and nullable.

Agent-provided event timestamps are accepted only when newer than the stored
value. `last_check_in` is always assigned by Django on successful receipt, not
trusted from the agent clock. A status is considered stale/offline when its
last check-in exceeds a documented multiple of the configured report interval;
no extra heartbeat history table is required for this feature.

## Status endpoint

Add token-scoped agent endpoint:

`POST /api/screens/<public-token>/status`

The token identifies the `Screen`; the agent does not need to send a mutable
screen name or arbitrary screen ID. JSON payload contains the runtime fields
above, current `content_id`, and a bounded list or summary of recent relevant
errors. The backend validates content membership for the screen and ignores
unknown content IDs.

Status posts are idempotent snapshots, not an append-only event log. A failed
status upload must not stop playlist playback. Backend validation errors are
logged by agent and retried on later intervals; malformed data never replaces a
valid stored status.

Keep endpoint authentication consistent with existing screen-token API and
HTTPS deployment. Do not expose host status through the public config response;
admin/runtime inspection is separate.

## Agent status collection

Add an `AgentRuntimeState` snapshot protected by a lock. Runner updates it on
state transitions:

- startup/config success or failure;
- browser start/recovery/navigation errors;
- successful page load with content ID and timestamp;
- current content activation;
- desired/actual power state;
- CEC, display, dialog, and injection warnings;
- screenshot capture/upload failures.

Add a dedicated reporter loop/thread so status continues while playlist code is
waiting, recovering Chromium, or handling an empty playlist. Use a separate
HTTP client/connection from configuration polling; do not concurrently read or
write one `httpx.Client` or one CDP websocket from two threads.

Report immediately at startup, then at configurable `status_interval` (default
60 seconds). Add TOML/CLI validation with a minimum interval and preserve
backward-compatible defaults. Reporter shutdown is bounded and must not delay
normal agent exit.

## Host metrics

Add best-effort host metrics collection with no third-party system-monitor
requirement:

- `os.getloadavg()` for load averages where available;
- Linux `/proc/meminfo` for total, available, used, and percentage memory;
- nullable values plus collection error when platform data is unavailable.

Never make missing host metrics a browser/playlist failure.

## Browser and display metadata

Expose/capture Chromium version from the local CDP `/json/version` response and
cache it for status reports. Use package `kiosk_agent.__version__` for agent
version.

Add a display probe abstraction in `display.py`:

- Wayland/labwc: best-effort output query (preferred configured output,
  including `HDMI-A-1`).
- X11 fallback: best-effort `xrandr` query.
- Parse output identity, active width/height, refresh rate, and transform.

Missing tools, disconnected output, or unparsable output produce nullable
metadata and `display_error`; they do not crash the agent. Keep configured
`WAYLAND_DISPLAY`, `DISPLAY`, and output selection in diagnostics/logs.

## Power and health state

Report desired power from manager configuration/override and actual power from
successful CEC state or `unknown` when unavailable. Do not infer physical power
when CEC is disabled or command failed.

Use a small health aggregator with deterministic precedence:

- `healthy`: configuration, browser, current page load, and required display
  path are working with no active errors;
- `degraded`: playback continues but telemetry, CEC, display metadata, host
  metrics, injection/dialog handling, or screenshot has a warning;
- `error`: browser/config/navigation cannot provide current playback or an
  unrecovered fatal runtime condition exists;
- `unknown`: startup has not produced enough evidence.

Keep latest browser/display error fields separate from the overall state. A
single custom CSS/JavaScript failure or auto-dismissed dialog must be reported
but must not by itself make content unhealthy or stop playback.

## Screenshot model and upload

Add `ScreenContentScreenshot` keyed uniquely by `(screen, content)`:

- screen foreign key;
- content foreign key;
- PNG file field;
- `captured_at`;
- health state at capture;
- optional bounded error summary / display metadata snapshot;
- `updated_at`.

This intentionally keeps only one current screenshot per screen/content pair.
When replacing, save new file then remove old storage object after successful
replacement. Deleting screen/content removes its screenshot. No screenshot
history is stored.

Add multipart endpoint:

`POST /api/screens/<public-token>/screenshots`

Fields:

- `content_id`;
- `captured_at`;
- `health_state`;
- optional error summary;
- PNG image bytes.

Validate that content is currently linked to screen, enforce a strict upload
size limit and PNG signature/content type, and reject malformed or oversized
uploads. Do not trust filename or client-provided screen identity. Replace
existing row/file only when incoming capture is newer.

Add admin read-only display/link for latest screenshots and runtime status.
No public screenshot listing endpoint is required.

## Screenshot capture policy

Add agent `screenshot_interval` config, default several minutes (recommended
300 seconds), with a minimum value. Capture no more than once per interval per
`(screen, content_id)` using a monotonic in-memory map. The interval is shared
when same content appears multiple times in one playlist.

Capture only the currently active content after a successful page load. Do not
capture normal snapshots while navigation/preload is visibly loading. Allow a
single rate-limited diagnostic capture after a navigation/browser error only
when an active target is available; mark it diagnostic in health metadata.

Use CDP `Page.captureScreenshot` (`png`, viewport/current surface) on the active
page. Integrate capture requests with BrowserController's serialized CDP
command path; reporter thread must not read the active websocket concurrently.
Recommended flow:

1. Reporter thread determines status and screenshot work.
2. Runner/browser loop performs capture at a safe point after page load.
3. Capture bytes remain in a bounded in-memory queue keyed by screen/content.
4. Reporter uploads bytes and drops them after success or bounded retry expiry.

Never write screenshots to profile, temp, or agent data directories. Upload
failure changes telemetry health/error state but does not stop playback.

## API/config compatibility

Keep `/api/screens/<public-token>/config` playlist behavior unchanged except for
adding stable `content_id` required to associate runtime data and screenshots.
Existing agents that do not report status continue to receive config normally.

Add status and screenshot interval settings to TOML/CLI/service configuration;
use defaults so existing services need no edits.

## Tests

Django tests:

- status endpoint token authorization and validation;
- timestamp monotonicity and server-owned check-in;
- host/display/power/error field persistence;
- stale status behavior;
- content membership validation;
- screenshot PNG/size validation;
- one-row replacement and old-file cleanup;
- newer-capture-only behavior;
- admin runtime/screenshot display.

Agent tests:

- host memory/load collectors and unavailable-platform fallbacks;
- browser version and display probe parsers/failures;
- runtime health transitions and thread-safe snapshots;
- status payload, interval scheduling, retries, and manager outage behavior;
- content ID tracking and last successful page load;
- screenshot interval enforcement per content;
- no capture before load and diagnostic capture rate limiting;
- CDP screenshot bytes and serialized command access;
- no local screenshot file creation;
- upload replacement/error handling without playlist crash.

Run Django and agent tests, migration checks, Ruff, Pyright, and lens
diagnostics. No board deployment during this change.
