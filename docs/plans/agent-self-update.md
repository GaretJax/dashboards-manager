# Agent Self-Update Plan

Status: implemented.

## Goal

Have each `kiosk-agent` periodically check Kiosk Manager for a newer packaged
agent, install it through persistent `uv`, refresh its config/systemd unit, and
restart itself. Playback must continue when update checks, downloads, or
installation fail. Successful installation and restart must be recorded in the
management event stream.

This plan depends on `docs/plans/one-command-agent-bootstrap.md`, which defines
how Manager builds and serves the agent wheel. It assumes agent installation
uses a persistent uv tool environment and a user systemd service.

## Version discovery

Agent learns about updates from a stable Manager package URL by inspecting an
HTTP redirect without following it:

```text
HEAD /downloads/kiosk-agent.whl
302 Location: /downloads/kiosk_agent-0.1.2-py3-none-any.whl
```

The stable endpoint is the same URL used by the bootstrap installer. Manager
redirects it to the exact wheel filename produced by `uv build`. The versioned
wheel URL is immutable and can be cached; the stable redirect is not cached.
The redirect endpoint and wheel are public read-only artifacts because they
contain no screen secret. Agent event reporting continues to use the existing
screen-token API.

Agent must set `follow_redirects=False`, require a redirect response and a
`Location` header, resolve relative locations against the manager URL, require
the same HTTPS origin and `/downloads/` path, and parse the filename with wheel
metadata utilities rather than a hand-written version regex. It compares the
parsed PEP 440 version with local `kiosk_agent.__version__`. Equal, older,
malformed, non-wheel, incompatible, or unsupported versions are ignored and
logged. No downgrade occurs through automatic update.

After detecting a newer filename, agent downloads that exact versioned URL
without following further redirects. It verifies response size limits, wheel
package name, wheel metadata version, Python requirement, and local SHA-256
before passing the file to uv. The redirect is the discovery signal; downloaded
wheel metadata and HTTPS same-origin checks protect installation integrity.

Default check policy:

- check once after initial configuration/startup;
- check every six hours thereafter;
- expose `update_interval` and `auto_update` in TOML/CLI for maintenance;
- rate-limit repeated redirect/download failures and never block playlist
  playback.

## Update lifecycle

Run update work at a runner loop boundary, outside CDP callbacks and without
holding the browser or telemetry locks:

1. Request the stable wheel URL with redirects disabled and validate the
   `Location` filename/version.
2. Emit `update_available` with current and remote versions.
3. Download the exact versioned wheel URL to an agent data-directory temporary
   file using bounded
   streaming I/O.
4. Verify maximum size, HTTPS/same-manager origin, SHA-256, wheel package
   name, and wheel metadata version. Never execute an unverified download.
5. Emit `update_install_started`.
6. Invoke persistent `uv tool install --force <temporary-wheel>` for the
   current target user. Dependencies resolve from wheel metadata using uv.
7. Verify the installed package/CLI reports the expected version.
8. Re-read and validate current config, preserving user values while applying
   defaults for new config keys. Write the validated config atomically.
9. Regenerate the systemd unit with the newly installed interpreter and current
   display/runtime settings. Do not start a second agent before old process
   shutdown.
10. Emit `update_installed` with versions and package digest.
11. Flush update events synchronously, then request `systemctl --user restart`
    for the active config instance.
12. New process emits `agent_restarted`/`agent_started` with running version and
    removes a one-shot restart marker after reporting it.

The current unit's stable config instance is the source of truth. Refreshing
must not replace the config with installer defaults or lose CEC, display,
profile, reporting, or injection-related settings. Add a dedicated service
refresh helper/CLI path rather than scraping systemd unit text.

Automatic updates require a named config and managed user systemd unit so
config/unit refresh and restart are unambiguous. Manual `kiosk-agent run`
invocations skip automatic installation and should use the explicit bootstrap
or service workflow first. The supported update path remains user systemd.

## Failure and recovery policy

Every failed stage emits `update_failed` with a bounded stage/error context:

- redirect response/Location/version validation;
- incompatible Python/package metadata;
- download/size/hash validation;
- uv installation;
- installed-version verification;
- config write or unit regeneration;
- service restart request.

Failures leave current playback and current installed version running. Keep
failed remote versions on a bounded cooldown so a bad release does not trigger
an update attempt every loop. Remove temporary wheel files on every path.
Protect config and unit writes with atomic replacement and retain a backup for
manual recovery. Do not automatically downgrade or run arbitrary post-install
scripts.

If uv cannot be found, the installation is not persistent, or systemd user
control is unavailable, report a clear event and continue the existing agent.
The update path must not require root or invoke sudo.

## Agent implementation

Add a small `update` module containing:

- redirect/Location validation and wheel filename parsing;
- PEP 440 version comparison;
- bounded streaming download and digest verification;
- wheel metadata/package validation;
- uv installation subprocess with timeout and captured bounded output;
- config/service refresh orchestration;
- cooldown and restart-marker handling.

Extend `ManagerClient` with:

- stable wheel URL;
- no-redirect version probe and `Location` validation;
- streaming versioned package download;
- existing event upload remains the only event transport.

Extend config/CLI/service interfaces:

- `update_interval` default `21600` seconds;
- `auto_update` default `true`;
- `kiosk-agent upgrade --check`/diagnostic command for manual inspection;
- `service refresh` or equivalent that re-renders the current unit using the
  installed interpreter without starting a duplicate process;
- machine-readable version output for post-install verification.

Keep version reporting in agent status and lifecycle events so Manager can show
installed version versus available version without parsing logs.

## Django implementation

- Make `/downloads/kiosk-agent.whl` return a no-cache redirect to the exact
  bundled wheel filename.
- Serve the exact wheel filename with immutable/cache-friendly headers.
- Ensure redirect target is generated from the artifact actually built into
  the Docker image; do not maintain a second version source.
- Add event vocabulary documentation for update lifecycle codes.
- Add operational/admin display of installed agent version and last update
  event when useful; do not add public package-management controls.

No package upload or arbitrary URL update endpoint is allowed. Manager owns the
release artifact; agent accepts only the validated same-origin redirect target.

## Event vocabulary

Use concise high-level events:

- `update_check_started` — `DEBUG`;
- `update_available` — `INFO`;
- `update_download_started` — `INFO`;
- `update_install_started` — `INFO`;
- `update_installed` — `INFO`;
- `update_restart_requested` — `INFO`;
- `agent_restarted` — `INFO`;
- `update_failed` — `WARNING` or `ERROR` depending on stage/recovery.

Include current/remote version, stage, bounded digest prefix, and retry/cooldown
context only. Never include wheel contents, credentials, or raw subprocess
output. Synchronous flush before restart is required so installation is visible
even though the old process exits immediately.

## Tests and verification

Django tests:

- stable wheel URL returns a no-cache redirect with exact full wheel filename;
- versioned wheel response is immutable and serves the packaged artifact;
- malformed/missing artifact and invalid redirect handling;
- same-origin path validation and cache/security headers.

Agent tests:

- current/remote version comparison, no downgrade, malformed Location;
- manager outage and rate-limited retries;
- package size/hash/metadata mismatch rejection;
- uv success/failure/timeout and installed-version verification;
- config preservation and atomic rewrite;
- systemd unit refresh and manual exec fallback;
- event ordering, synchronous flush, restart marker, and no playback impact;
- update interval/disable configuration.

Integration/build checks:

- Docker image contains wheel and redirect-target metadata;
- wheel served by Manager installs through uv;
- fake uv/systemd integration exercises successful restart path;
- full Django/agent suites, Ruff, Pyright, migration checks, Docker Compose
  validation, and lens diagnostics.

Verify on Docker/test infrastructure only. No board deployment or live
self-update rollout without explicit approval.

## Commits

Keep work reviewable:

1. commit this plan;
2. implement Manager stable redirect and artifact download endpoint;
3. implement agent version/update client and validation;
4. implement uv installation, config/unit refresh, and restart flow;
5. add update events, admin/status visibility, tests, and docs;
6. use `fixup!` commits for review revisions.
