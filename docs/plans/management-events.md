# Management Event Reporting Plan

Status: implemented.

## Goal

Add a separate Django `Event` model for concise, high-value operational events
and issues. Keep current runtime status as a latest snapshot; use events as a
short-retention timeline. Do not stream every Chromium/CDP event to Django.

## Event model

Create `kiosks.Event` with:

- `screen` foreign key, required;
- optional `content` foreign key for content-scoped events;
- optional URL snapshot, bounded and sanitized;
- `code`, a flexible normalized string such as `navigation_failed`,
  `readiness_timeout`, or `agent_started`;
- `level`, using standard logging levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`,
  `CRITICAL`;
- short human-readable `message`;
- agent `occurred_at` timestamp;
- server `received_at` timestamp;
- optional stable `fingerprint`/incident key;
- bounded JSON `details` for allow-listed context only.

Do not use a rigid database choice list for event codes. Validate code format
and document supported high-level codes. Keep messages/details bounded, redact
credentials/tokens and URL query secrets, and never store raw browser event
payloads.

Add indexes for `(screen, -received_at)`, `(screen, code, -received_at)`, and
retention by `received_at`. Event rows are append-only from agent API; admin
users get read-only inspection.

## Event vocabulary and levels

Agent maps internal failures to a small vocabulary:

- `agent_started`, `agent_restarted`, `agent_shutdown` — `INFO`;
- `healthy`, `display_power_on`, `display_power_off` — `INFO`;
- `config_fetched`, `page_loaded` — `DEBUG`;
- `loading`, `preloading` — `DEBUG` or `INFO`;
- `navigation_failed`, `readiness_timeout`, `script_error`, `unexpected_url`,
  `display_control_failed` — `WARNING` or `ERROR` based on recovery result;
- `browser_target_failed` — `ERROR`;
- unrecoverable process/runtime conditions — `CRITICAL`;
- update lifecycle: `update_check_started`, `update_available`, `update_started`,
  `update_download_started`, `update_install_started`, `update_installed`,
  `update_restart_requested`, `agent_restarted`, and `update_failed`.

Exact mapping should preserve logging-level semantics: recoverable page/CEC/
telemetry issues are warnings, failed recovery or unavailable browser/display
control is error, and process-threatening conditions are critical.

Emit only state transitions, issue occurrences, recovery summaries, and major
lifecycle/config events. Do not emit every CDP message, load event, dialog, or
poll iteration. Existing logs remain detailed locally.

## Transient versus persistent issues

Keep `Event` append-only and use existing/latest `ScreenRuntimeStatus` as
current truth. Agent maintains a bounded issue tracker keyed by code, content
identity, and URL:

- emit first occurrence immediately;
- rate-limit repeated occurrences while issue remains active;
- emit `healthy`/`page_loaded` recovery event when playback succeeds again;
- include optional fingerprint and occurrence/retry count in details.

Management UI distinguishes a transient reload/failure from a persistent kiosk
by combining ordered events, repeated fingerprints, current runtime health,
last successful page load, and stale check-in status. A failure followed quickly
by `loading`/`page_loaded` is transient; repeated failures with no recovery and
an unhealthy/stale runtime status are persistent. No attempt is made to infer
health from every low-level browser event.

## Agent event API

Add token-scoped batch endpoint:

`POST /api/screens/<public-token>/events`

Request body:

```json
{
  "events": [
    {
      "code": "navigation_failed",
      "level": "WARNING",
      "message": "navigation failed",
      "content_id": 12,
      "url": "https://example.invalid/dashboard",
      "occurred_at": "2026-01-01T12:00:00Z",
      "fingerprint": "navigation_failed:12",
      "details": {"retry_count": 2}
    }
  ]
}
```

Validate token through screen route, batch count, code/level/message lengths,
allowed details keys/types, content membership, and timestamp bounds. Server
sets `received_at`; it must not trust agent-provided screen identity. Reject or
partially accept malformed events with a clear response; preferred behavior is
atomic batch validation so one bad event does not create an ambiguous partial
batch.

No public event read endpoint is required. Admin/runtime UI reads events via
Django ORM. HTTPS and existing screen-token authentication remain required.

Event upload failures must not stop playlist playback. Use a bounded in-memory
queue with immediate best-effort post, exponential retry, and rate-limited
logging. Drop oldest events after queue capacity with a local warning rather
than writing an unbounded disk spool.

## Django admin

Register `Event` as read-only:

- list screen, level, code, content, message, occurred/received timestamps;
- filter level, code, screen, and time;
- search screen/content/message/fingerprint;
- disable add/change/delete actions except retention task deletion;
- show latest events inline or linked from `ScreenAdmin`.

Add a concise event timeline to screen operational inspection. Keep raw
technical logs out of normal UI; expose message plus allow-listed details only.

## Celery retention cleanup

Introduce Celery infrastructure because project currently has no Celery setup:

- add Celery dependency and broker configuration;
- add `kiosk_manager/celery.py` app with Django settings autodiscovery;
- add `kiosks.tasks.delete_expired_events`;
- configure `EVENT_RETENTION_DAYS=30` by default, overridable by environment;
- schedule cleanup daily through Celery Beat using server timezone;
- run worker and beat in deployment, and add local Docker Compose broker/worker
  services or documented equivalents.

Cleanup uses server `received_at`, deletes rows older than retention, and runs
in bounded batches when volume is high. Task is idempotent and reports deleted
count. Do not delete current runtime status or latest screenshots through this
task.

## Integration points

- Agent runner emits lifecycle/config/page/power/recovery events.
- Browser controller exposes high-level failure categories instead of raw CDP
  events.
- Content injection and dialog handlers emit `script_error` or displayable
  warnings through the same event queue, without crashing playback.
- Operational status reporter remains periodic snapshot reporting; Event posts
  happen immediately for issues/transitions and are not used as heartbeat.
- Screenshot metadata may include current health/event fingerprint, but each
  screenshot remains governed by screenshot retention/replacement rules.

## Tests

Django tests:

- event model validation, levels, codes, bounds, indexes;
- token authorization and content membership;
- atomic batch validation and server-owned timestamps;
- URL/detail redaction and malformed payload handling;
- admin read-only behavior and timeline ordering;
- retention task deletes only expired events and preserves newer/runtime data.

Agent tests:

- internal failure-to-event mapping and level selection;
- transition/recovery event behavior and issue rate limiting;
- content/URL/timestamp/fingerprint context;
- batch queue, retries, overflow, manager outage, and no playlist impact;
- no raw CDP event leakage.

Run Django and agent tests, Celery task tests, migration checks, Ruff, Pyright,
and lens diagnostics. Verify worker/beat configuration in deployment without
board rollout.
