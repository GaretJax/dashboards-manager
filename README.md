# Kiosk Manager

Django application for managing kiosk screens and ordered content playlists.

Each screen has a public token URL. Its display loads configured content,
switches between playlist entries after their durations, and polls the
read-only Ninja API for playlist changes.

## Local development

Python 3.14 and Docker are supported. PostgreSQL is used in development and
tests.

```shell
cp .env.example .env
docker compose run --rm web python manage.py collectstatic --noinput
docker compose up --build
```

Open <https://dashboards.local.aldryn.net/admin/> to create a superuser and
configure screens. Uploaded media persists under `.artifacts/media` in local
Docker Compose. External access is HTTPS-only; TLS terminates at external
LB. A screen detail page exposes its public display URL. The
token can be rotated with the **Rotate public token** detail action; existing
URLs stop working immediately.

Display API and content:

- `GET /api/screens/<public-token>/config`
- `/screens/<public-token>/`
- `POST /api/screens/<public-token>/status`
- `POST /api/screens/<public-token>/events`
- `POST /api/screens/<public-token>/screenshots`

Local Compose starts RabbitMQ plus Celery worker/beat services for event
retention. Content owns preloading configuration. `preload_delay_seconds` starts loading
before display; `preload_timeout_seconds` displays content after timeout from
request start, regardless of load state or delay. Content can use external URLs
or one uploaded self-contained HTML file and can be reused across screens.

Useful commands:

```shell
docker compose run --rm web python manage.py collectstatic --noinput
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py createsuperuser
docker compose run --rm test
```

## Deployment

Pushes to `main` run tests inside the Docker test image, publish the production
image to `ghcr.io/garetjax/dashboards-manager`, and deploy it to Divio. Pull
requests run the test and image-build jobs without publishing or deploying.

Configure these values in the `live` GitHub environment:

- Secret `DIVIO_DEPLOY_TOKEN`
- Variable `DIVIO_APP_UUID`
- Variable `BACKEND_DOMAIN`

Divio uses `Dockerfile.divio`, which references the published `latest` image.
Set production Django and database settings through Divio environment
variables; `.env.example` lists application configuration keys.

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

For Chromium background preloading and host setup, see
[`agent/README.md`](agent/README.md#background-preloading). For a screen
created in admin, copy its **Agent installation** command and run it on a
Debian-family kiosk host:

```shell
curl -fsSL 'https://manager.example/install.sh?screen=SCREEN_TOKEN' | bash
```
