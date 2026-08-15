# One-Command Agent Bootstrap Plan

Status: implemented.

## Goal

Serve the packaged `kiosk-agent` from Kiosk Manager and provide an administrator-
generated command that turns a Debian-family graphical kiosk host into a
running agent with one command:

```shell
curl -fsSL 'https://manager.example/install.sh?screen=SCREEN_TOKEN' | bash
```

The screen is created first by an administrator in Django admin. Bootstrap must
not create screens or expose a public screen-creation API. The install command
uses the screen's existing public token, which is already the agent credential
for configuration and reporting. Rotating the token invalidates old install
commands and installed agents.

Scope is Debian and derivatives with `apt`; target setup uses the invoking user
and a user systemd service. Board deployment remains out of scope.

## Security and URL contract

Add a root-level Django route:

`GET /install.sh?screen=<public-token>`

The route validates that the screen exists and returns a dynamically rendered
shell script. It embeds only:

- manager base URL, including `SITE_BASE_PATH`, derived from the effective HTTPS
  request origin;
- existing screen public token;
- versioned agent wheel URL.

Use shell-quoting for every embedded value. Return `text/x-shellscript`,
`Cache-Control: no-store`, and reject missing/unknown screen tokens. Do not put
numeric database IDs in a public installer URL: the public token is both the
current agent identity and the least-surprising screen identifier for this
flow. The token is already displayed in the admin detail form and used by the
agent API.

Add public, read-only wheel download routes:

- `GET`/`HEAD /downloads/kiosk-agent.whl` returns a no-cache redirect;
- the redirect targets `/downloads/<full-wheel-filename>.whl`, which serves the
  immutable artifact.

The wheel contains no screen secret. Set immutable/cache-friendly headers for
the versioned wheel; keep the stable redirect and dynamic installer response
uncached. HTTPS-only deployment rules remain unchanged.

## Admin experience

Extend `ScreenAdmin` detail view with a read-only **Agent installation** section:

- install URL;
- copyable `curl -fsSL ... | bash` command;
- short warning that the command contains the screen's agent credential;
- current wheel/agent version if available.

Use URL reversing and `SITE_BASE_PATH` rather than duplicating route strings.
Keep the command updated automatically after public-token rotation. Do not show
installer commands in the screen list or add a public screen-creation action.

## Docker packaging

Build agent wheel during image construction with `uv build`, then copy it into
the final image:

1. `Dockerfile` application stage builds `agent` into a dedicated artifact
   directory after source is copied.
2. Runtime stage copies only the wheel artifact needed by the download view.
3. `Dockerfile.dev` builds the same artifact for local development.
4. Production/Divio images inherit the artifact from the published image.
5. The Django view locates the artifact through a setting or deterministic
   path, failing healthfully with a server error if packaging omitted it.

Agent Python dependencies remain wheel metadata dependencies. `uv tool install`
resolves them into the persistent tool environment; they are not copied into
the Django image or vendored into the shell script. Pin/build using the agent
lockfile and test that the wheel filename/version matches the served path.

## Installer behavior

Create a strict Bash script with `set -Eeuo pipefail`, clear failures,
cleanup traps, and no unquoted interpolated values. Keep shell scope narrow:
the script installs Debian dependencies and the persistent agent wheel, then
hands all kiosk configuration/setup to `kiosk-agent bootstrap`.

### Preconditions

- require Bash, `curl`, `sudo` when not root, and a known target user;
- detect whether `/dev/tty` is available for an interactive bootstrap; when it
  is unavailable, pass non-interactive mode and fail on ambiguous choices;
- parse `/etc/os-release` and require `ID=debian` or a Debian-family value in
  `ID_LIKE`; fail clearly for non-Debian hosts;
- require HTTPS manager URL and reject a missing/invalid embedded screen token;
- preserve the invoking user when run through `sudo`; do not install the user
  service or config as root unless the target user is explicitly root;
- pass manager URL, screen token, wheel URL, and target-user context to the
  agent subcommand; do not generate config or systemd files in shell;
- never overwrite an existing config without the agent subcommand's explicit
  reinstall/force policy.

### Host dependencies

As root through `sudo apt-get`, install the supported kiosk dependencies:

- `ca-certificates`, `curl`, and a supported Python runtime/bootstrap tooling;
- `chromium` from an available Debian-family apt repository;
- `labwc` and `wtype` for the Wayland target;
- `cec-utils` for HDMI-CEC control;
- packages required by the selected Chromium build.

Do not silently install Ubuntu snap Chromium. Verify an apt candidate and fail
with remediation when the distribution does not provide a compatible package.
Record package-manager output in the terminal; do not hide privileged changes.
Add the target user to the required device group for CEC when present, and warn
that an existing login session may need to restart before device permissions
apply.

Install persistent `uv` for the target user using a pinned, documented uv
bootstrap method. Add its bin directory to the script's process `PATH`, then
run as target user:

```shell
uv tool install --force <manager-wheel-url>
```

The wheel URL must remain same-origin with the installer unless an explicit
future policy changes that. Do not use `uvx` for the systemd service. Verify
that `kiosk-agent --version` works before handing off.

### Delegation to agent bootstrap

The script invokes one agent-owned setup command after installation:

```shell
kiosk-agent bootstrap \
  --manager "$MANAGER_URL" \
  --screen "$SCREEN_TOKEN"
```

When a terminal is available, run this command against `/dev/tty` so
`curl | bash` does not consume interactive input. Support explicit
`--non-interactive`/environment inputs for automation; fail rather than guess
when required values are ambiguous.

Agent bootstrap owns all remaining setup:

- discover target UID/home/runtime and active X11/Wayland sessions;
- select a display when multiple displays or compositor environments exist;
- default Wayland to `wayland-0` and `/run/user/<uid>` only when unambiguous;
- detect Chromium and offer a choice when multiple browser binaries exist;
- detect CEC ports and let the operator choose one or disable CEC;
- choose/confirm config name and confirm replacing existing config;
- write validated TOML through `dump_config`/`merge_config`, preserving manager,
  screen, display, CEC, profile, and operational reporting values;
- optionally install the labwc cursor binding through the existing agent path;
- install/enable/start the user systemd unit through service helpers;
- wait for startup and run doctor with bounded retries;
- print config, unit, logs, display URL, and any relogin/reboot requirement.

Interactive prompts must be concise, deterministic, and testable. A graphical
session need not exist during SSH setup: bootstrap may write detected/default
values and install the unit, but doctor must clearly report unavailable display
or CDP rather than claiming success. Never modify display-manager autologin
policy silently.

### Shell-to-agent boundary

Shell performs only:

1. Debian-family validation and privileged apt dependency installation;
2. persistent uv installation for target user;
3. wheel installation and version verification;
4. invocation of `kiosk-agent bootstrap`.

Agent performs config generation, display/CEC selection, systemd installation,
startup, doctor validation, and final operator guidance. This keeps setup logic
unit-testable in Python and lets future package installers reuse the same
bootstrap command.

## Agent CLI changes

Add `kiosk-agent bootstrap` as the single owner of post-install setup. Reuse
`config`, `doctor`, `wayland setup`, and `service install` helpers underneath
it, rather than duplicating their behavior in shell:

- accept `--manager`, `--screen`, optional `--config`, and display/CEC/profile
  overrides;
- support interactive prompts through `/dev/tty` for display/backend/browser/
  CEC/config choices;
- support `--non-interactive` and explicit values, failing on ambiguity rather
  than silently selecting the wrong monitor;
- preserve `status_interval` and `screenshot_interval` through service config;
- run doctor with bounded startup retries and return stable exit status;
- ensure service startup uses the persistent uv tool interpreter and current
  target user's config;
- keep current `--manager`/`--screen` token contract unchanged.

The command may expose machine-readable summary output for shell automation,
but human setup remains understandable without it. Avoid adding manager-
creation logic to the agent. Bootstrap failures must not leave a running
half-configured service; use atomic config writes and clean up a unit that was
created but could not be started when safe.

## Django implementation

- Add installer/wheel views and URL names.
- Add setting for packaged wheel location and redirect/full-filename handling.
- Add safe dynamic shell template rendering containing only bootstrap inputs.
- Add admin computed fields and tests.
- Include route under `SITE_BASE_PATH` and verify forwarded HTTPS origin
  handling.
- Keep screen token authorization unchanged for agent config/status/events.

No new screen-creation API is needed for this flow. Admin remains the screen
provisioning boundary.

## Tests and verification

Django tests:

- valid screen returns installer script with correct HTTPS manager URL, base
  path, token, and wheel URL;
- missing/unknown token returns 4xx;
- script response has no-store headers and shell-safe interpolation;
- wheel response serves the packaged artifact with correct content type;
- admin detail renders command and token rotation changes it;
- disabled/deleted screens do not produce usable installer commands;
- URL generation works behind configured HTTPS proxy settings.

Agent tests:

- bootstrap preserves operational intervals and autodetected display values;
- interactive display/browser/CEC/config choices through a fake terminal;
- non-interactive mode rejects ambiguous or missing required values;
- config path and target-user environment handling;
- CEC absent/present detection and optional fallback;
- generated systemd unit uses persistent interpreter and config instance;
- doctor startup retry, summary, and exit behavior.

Installer/Docker tests:

- `bash -n install.sh` or rendered installer scripts;
- shell installs mocked Debian dependencies and wheel, then invokes bootstrap;
- shell never writes config or systemd files itself;
- mocked Debian apt/uv failure paths;
- non-Debian rejection and root/target-user handling;
- Docker build creates wheel and runtime image contains it;
- wheel installs with uv and imports on supported Python;
- Compose image serves both download routes;
- full Django and agent suites, Ruff, Pyright, migration checks, Docker Compose
  validation, and lens diagnostics.

Verify on Docker/test infrastructure only. No board deployment or live HDMI-
CEC rollout without explicit approval.

## Commits

Keep plan and implementation reviewable:

1. commit this plan;
2. implement wheel packaging/download route;
3. implement admin installer command;
4. implement agent CLI/config/service bootstrap support;
5. implement installer script and Debian dependency handling;
6. add tests/docs and use `fixup!` commits for review revisions.
