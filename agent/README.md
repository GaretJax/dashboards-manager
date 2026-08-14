# Kiosk Agent

`kiosk-agent` runs Chromium as a top-level navigation kiosk. It polls Kiosk
Manager, cycles configured URLs, and controls Chromium through the local Chrome
DevTools Protocol endpoint.

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

`uvx` is suitable for one-off runs. Service installation requires a persistent
installation because uvx environments live in cache:

```shell
uv tool install kiosk-agent
kiosk-agent service install \
  --manager https://manager.example \
  --screen SCREEN_TOKEN
```

## Commands

- `run` launches/supervises Chromium and cycles playlist URLs.
- `config` prints current playlist configuration.
- `doctor` checks runtime, display, browser, CDP, systemd, and API readiness.
- `service install`, `uninstall`, `show-unit`, `status`, `start`, `stop`,
  `restart`, `enable`, `disable`, `logs`, and `doctor` manage systemd.

`doctor` detects Wayland before X11. For Wayland, set
`WAYLAND_DISPLAY` and `XDG_RUNTIME_DIR`; for X11, set `DISPLAY`:

```shell
WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 \
  kiosk-agent doctor
DISPLAY=:0 kiosk-agent doctor
```

User services are default. Graphical autologin starts user services after boot;
linger is optional. `--scope system` is available for setups that manage a
separate kiosk user explicitly.
