# Kiosk Manager

Django application for managing kiosk screens and ordered URL playlists.

Each screen has a public token URL. Its page loads an iframe, switches between
configured URLs after their durations, and polls the read-only Ninja API for
playlist changes.

## Local development

Python 3.14 and Docker are supported. PostgreSQL is used in development and
tests.

```shell
cp .env.example .env
docker compose up --build
```

Open <https://dashboards.local.aldryn.net/admin/> to create a superuser and
configure screens. External access is HTTPS-only; TLS terminates at external
LB. A screen detail page exposes its public display URL. The
token can be rotated with the **Rotate public token** detail action; existing
URLs stop working immediately.

Display API and page:

- `GET /api/screens/<public-token>/config`
- `/screens/<public-token>/`

Useful commands:

```shell
docker compose run --rm web uv run python manage.py migrate
docker compose run --rm web uv run python manage.py createsuperuser
docker compose run --rm test
```

## Browser kiosk

Use Chromium kiosk mode on a Pi 3/4/Zero 2 W-class device:

```shell
chromium --kiosk --noerrdialogs --disable-infobars \
  --no-first-run --start-maximized https://manager.example/screens/TOKEN/
```

Original Raspberry Pi Zero hardware is not recommended for modern Chromium.
The target URL must permit iframe embedding; browser settings cannot generally
override a target site's `X-Frame-Options` or CSP `frame-ancestors` policy.

## Top-level browser agent

For sites that block iframe embedding, use the separate `agent/` package. It
navigates Chromium directly through CDP:

```shell
uv tool install ./agent
kiosk-agent doctor --manager https://manager.example --screen TOKEN
kiosk-agent service install --manager https://manager.example --screen TOKEN
```
