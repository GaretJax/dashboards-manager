# Kiosk Agent

`kiosk-agent` runs Chromium as a top-level navigation kiosk. It polls Kiosk
Manager, cycles configured URLs, and controls Chromium through the local Chrome
DevTools Protocol endpoint.

## Host setup

Target Debian/Raspberry Pi OS host needs:

- Python 3.11+
- `uv`
- Chromium
- Wayland compositor (`labwc`) or X11
- `wtype` for Wayland cursor hiding
- `cec-utils` for HDMI-CEC power control
- user systemd + graphical autologin

Install common packages:

```shell
sudo apt update
sudo apt install chromium labwc wtype cec-utils
```

No virtual-output tools are required. `grim` is optional for screenshots and
diagnostics.

Install agent persistently from this repository or a built wheel:

```shell
uv tool install --force ./agent
# or: uv tool install --force ./agent/dist/kiosk_agent-0.1.1-py3-none-any.whl
```

Set up graphical autologin into labwc. Agent user must own its Wayland session
and have `WAYLAND_DISPLAY` and `XDG_RUNTIME_DIR`, normally:

```shell
export WAYLAND_DISPLAY=wayland-0
export XDG_RUNTIME_DIR=/run/user/$(id -u)
```

Create a screen in Manager and copy its HTTPS manager URL and screen token.
Agent needs outbound HTTPS access to Manager and each dashboard URL.

Background mode needs no virtual output. To hide cursor, install the
labwc binding with `wayland setup` and ensure `wtype` is installed; agent
presses it when starting:

```xml
<keybind key="W-A-F8">
  <action name="HideCursor" />
</keybind>
```

Install cursor binding:

```shell
WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 \
  kiosk-agent wayland setup
```

`wayland setup --dry-run` prints config and writes nothing. Existing labwc
configuration is preserved; one marked cursor block is replaced on reruns.

## Development

```shell
uv sync
uv run pytest
uv run kiosk-agent --help
```

The package supports Python 3.11+ and can run directly with `uvx`:

```shell
uvx --from ./agent kiosk-agent run \
  --manager https://manager.example \
  --screen SCREEN_TOKEN
```

`uvx` is suitable for one-off runs. For an administrator-
created screen, Manager serves a one-command Debian bootstrap:

```shell
curl -fsSL 'https://manager.example/install.sh?screen=SCREEN_TOKEN' | bash
```

Shell installs host dependencies and the wheel; `kiosk-agent bootstrap` handles
interactive display/CEC selection, config generation, systemd setup, and doctor
validation.

Service installation requires a persistent installation because uvx environments
live in cache:

```shell
uv tool install kiosk-agent
kiosk-agent service install \
  --manager https://manager.example \
  --screen SCREEN_TOKEN
```

## Commands

- `run` launches/supervises Chromium and cycles playlist content. Use
  `--status-interval` and `--screenshot-interval` to tune operational reports
  (defaults: 60 and 300 seconds). Use `--log-level DEBUG|INFO|WARNING|ERROR|CRITICAL` or
  `KIOSK_AGENT_LOG_LEVEL` to control verbosity. The selected level is stored
  in generated systemd units. HTTPX request lines are DEBUG-level.
- `config` prints current playlist, preload, and power configuration.
- `bootstrap` interactively configures display/CEC, writes config, installs the
  user service, and validates startup. Use `--non-interactive` only with
  unambiguous host defaults.
- `update --check` checks stable Manager wheel redirect for a newer agent.
- `cec list` and `cec detect` inspect HDMI-CEC adapters.
- `doctor` checks runtime, display, browser, CEC, CDP, systemd, and API readiness.
- `service install`, `uninstall`, `show-unit`, `status`, `start`, `stop`,
  `restart`, `enable`, `disable`, `logs`, and `doctor` manage systemd.

View user-unit logs with:

```shell
kiosk-agent service logs --scope user --lines 200
kiosk-agent service logs --scope user --follow
```

When user journal storage is unavailable, `logs` filters system journal entries
by `_SYSTEMD_USER_UNIT` and service UID. With `sudo`, original UID is detected
from `SUDO_UID`.

`doctor` detects Wayland before X11. For Wayland, set
`WAYLAND_DISPLAY` and `XDG_RUNTIME_DIR`; for X11, set `DISPLAY`:

```shell
WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 \
  kiosk-agent doctor
DISPLAY=:0 kiosk-agent doctor
```

Agent always preloads pages in background targets. `preload_delay_seconds`
starts loading before scheduled display. `preload_timeout_seconds` counts from
request start and displays target content when it expires, regardless of load
state or remaining preload delay. Both values belong to reusable content.
Content may define CSS plus JavaScript before-page-scripts and after-load
injections. Injection failures are logged without stopping playback. Native
JavaScript dialogs are automatically handled so they cannot block the kiosk.
The agent periodically reports host/display/browser health and uploads one
latest in-memory diagnostic screenshot per content item at the configured
interval; screenshots are not written locally. Persistent agents check
`/downloads/kiosk-agent.whl` periodically, inspect its redirect filename, verify
wheel metadata, install newer versions through uv, refresh their unit, and
restart. Update failures do not stop playback; installation/restart events are
reported to Manager.

## HDMI-CEC power schedules

Pass CEC adapter path with `--cec-port`:

```shell
kiosk-agent run --config lobby --cec-port /dev/cec0
kiosk-agent cec list
kiosk-agent cec detect
kiosk-agent doctor --cec-port /dev/cec0
```

Screen power-on and power-off schedules use RRULE fields. Agent sends
`on 0` and `standby 0` through `cec-client` when latest schedule occurrence
changes state.

Background tabs can fail for dashboards that defer rendering while
`document.visibilityState` is `hidden`; focus emulation and Chromium flags
are enabled to keep those dashboards rendering.

Run directly:

```shell
WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 \
  kiosk-agent run \
  --manager https://manager.example \
  --screen SCREEN_TOKEN \
  --cec-port /dev/cec0
```

TOML config files live in platformdirs config directory, normally
`~/.config/kiosk-agent/`. Example `lobby.toml`:

```toml
manager = "https://manager.example"
screen = "SCREEN_TOKEN"
cec_port = "/dev/cec0"
status_interval = 60
screenshot_interval = 300
update_interval = 21600
auto_update = true
wayland_display = "wayland-0"
runtime_dir = "/run/user/1000"
```

Run with `kiosk-agent run --config lobby`; command-line options override TOML.

`service install` writes named TOML config and installs one idempotent template
unit. Multiple monitors can run separate instances:

```shell
kiosk-agent service install --config left \
  --manager https://manager.example --screen LEFT_TOKEN --cec-port /dev/cec0
kiosk-agent service install --config right \
  --manager https://manager.example --screen RIGHT_TOKEN --cec-port /dev/cec1
kiosk-agent service status --config left
kiosk-agent service logs --config right --lines 200
```

This installs `kiosk-agent@.service` and starts
`kiosk-agent@left.service` / `kiosk-agent@right.service`. `service install
--dry-run` does not write TOML or systemd files. `service show-unit` prints
template unit without installation.

When launching Chromium, agent closes stale page targets left by previous runs.
User services are default. Graphical autologin starts user services after boot;
linger is optional. `--scope system` is available for setups that manage a
separate kiosk user explicitly.
