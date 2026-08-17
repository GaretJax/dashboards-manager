import json
from datetime import UTC, datetime

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

import pytest

from kiosk_manager.kiosks.models import (
    Content,
    Event,
    Screen,
    ScreenContent,
)

HTML_CONTENT = "<!doctype html><h1>Embedded dashboard</h1>"


@pytest.mark.django_db
def test_agent_wheel_redirect_and_install_script(client, tmp_path):
    wheel = tmp_path / "kiosk_agent-0.1.2-py3-none-any.whl"
    wheel.write_bytes(b"fake wheel")
    screen = Screen.objects.create(name="Lobby Dashboard")

    with override_settings(KIOSK_AGENT_WHEEL_DIR=tmp_path):
        redirect_response = client.head("/downloads/kiosk-agent.whl")
        script_response = client.get(
            f"/install.sh?screen={screen.public_token}"
        )
        wheel_response = client.get(
            "/downloads/kiosk_agent-0.1.2-py3-none-any.whl"
        )

    assert redirect_response.status_code == 302
    assert (
        redirect_response["Location"]
        == "/downloads/kiosk_agent-0.1.2-py3-none-any.whl"
    )
    assert script_response.status_code == 200
    assert "kiosk-agent bootstrap" in script_response.text
    assert screen.public_token in script_response.text
    assert "DEFAULT_CONFIG_NAME=lobby-dashboard" in script_response.text
    assert "Config name [${DEFAULT_CONFIG_NAME}]" in script_response.text
    assert 'run_command "${APT[@]}" update' in script_response.text
    assert 'uv tool install --force "$WHEEL_URL"' in script_response.text
    assert "service logs" in script_response.text
    assert '--config "$CONFIG_PATH"' in script_response.text
    assert script_response.text.index('"${APT[@]}" update') < (
        script_response.text.index("apt-cache policy chromium")
    )
    assert "dpkg-query -W" in script_response.text
    assert script_response["Cache-Control"] == "no-store"
    assert b"".join(wheel_response.streaming_content) == b"fake wheel"
    assert "immutable" in wheel_response["Cache-Control"]


@pytest.mark.django_db
def test_screen_config_api_returns_ordered_content(client):
    screen = Screen.objects.create(name="Lobby")
    second = Content.objects.create(url="https://example.com/second")
    first = Content.objects.create(url="https://example.com/first")
    ScreenContent.objects.create(
        screen=screen,
        content=second,
        duration_seconds=20,
        order=2,
    )
    ScreenContent.objects.create(
        screen=screen,
        content=first,
        duration_seconds=10,
        order=1,
    )

    response = client.get(f"/api/screens/{screen.public_token}/config")

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store, no-cache, must-revalidate"
    payload = response.json()
    assert payload["version"]
    assert "timezone" not in payload
    assert "on_schedule" not in payload
    assert "off_schedule" not in payload
    assert payload["items"] == [
        {
            "content_id": first.pk,
            "url": "https://example.com/first",
            "duration_seconds": 10,
            "order": 1,
            "preload_delay_seconds": 0.0,
            "preload_timeout_seconds": 30,
            "injected_css": None,
            "injected_javascript_before": None,
            "injected_javascript_after": None,
        },
        {
            "content_id": second.pk,
            "url": "https://example.com/second",
            "duration_seconds": 20,
            "order": 2,
            "preload_delay_seconds": 0.0,
            "preload_timeout_seconds": 30,
            "injected_css": None,
            "injected_javascript_before": None,
            "injected_javascript_after": None,
        },
    ]


@pytest.mark.django_db
def test_screen_config_api_returns_power_status(client):
    screen = Screen.objects.create(name="Lobby")

    response = client.get(f"/api/screens/{screen.public_token}/config")

    payload = response.json()
    assert "power_override" not in payload
    assert payload["desired_power_state"] == "on"
    assert payload["reported_power_state"] == "unknown"
    assert payload["reported_power_at"] is None
    assert payload["pending_command"] is None


@pytest.mark.django_db
def test_screen_state_api_updates_report_and_acknowledges_restart(client):
    screen = Screen.objects.create(name="Lobby")
    command = screen.request_agent_restart()

    response = client.post(
        f"/api/screens/{screen.public_token}/state",
        data=json.dumps(
            {
                "actual_power_state": "on",
                "command_id": str(command.id),
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reported_power_state"] == "on"
    assert payload["reported_power_at"]
    assert (
        datetime.fromisoformat(
            payload["reported_power_at"].replace("Z", "+00:00")
        ).tzinfo
        == UTC
    )
    assert payload["pending_command"] is None
    command.refresh_from_db()
    assert command.acknowledged_at is not None


@pytest.mark.django_db
def test_screen_config_api_hides_schedule_and_override(client):
    screen = Screen.objects.create(
        name="Lobby",
        on_schedule="DTSTART:20260101T080000\nRRULE:FREQ=DAILY",
        off_schedule="DTSTART:20260101T220000\nRRULE:FREQ=DAILY",
    )

    response = client.get(f"/api/screens/{screen.public_token}/config")

    payload = response.json()
    assert "timezone" not in payload
    assert "on_schedule" not in payload
    assert "off_schedule" not in payload


@pytest.mark.django_db
def test_screen_config_api_applies_content_preload_settings(client):
    screen = Screen.objects.create(name="Lobby")
    inherited = Content.objects.create(
        url="https://example.com/inherit",
        preload_delay_seconds=4,
        preload_timeout_seconds=45,
    )
    override = Content.objects.create(
        url="https://example.com/override",
        preload_delay_seconds=2.5,
        preload_timeout_seconds=10,
    )
    ScreenContent.objects.create(screen=screen, content=inherited, order=1)
    ScreenContent.objects.create(screen=screen, content=override, order=2)

    response = client.get(f"/api/screens/{screen.public_token}/config")

    assert response.json()["items"] == [
        {
            "content_id": inherited.pk,
            "url": "https://example.com/inherit",
            "duration_seconds": 30,
            "order": 1,
            "preload_delay_seconds": 4.0,
            "preload_timeout_seconds": 45,
            "injected_css": None,
            "injected_javascript_before": None,
            "injected_javascript_after": None,
        },
        {
            "content_id": override.pk,
            "url": "https://example.com/override",
            "duration_seconds": 30,
            "order": 2,
            "preload_delay_seconds": 2.5,
            "preload_timeout_seconds": 10,
            "injected_css": None,
            "injected_javascript_before": None,
            "injected_javascript_after": None,
        },
    ]


@pytest.mark.django_db
def test_screen_config_api_returns_content_injections(client):
    screen = Screen.objects.create(name="Lobby")
    content = Content.objects.create(
        url="https://example.com",
        injected_css="body { display: none; }",
        injected_javascript_before="window.before = true;",
        injected_javascript_after="window.after = true;",
    )
    ScreenContent.objects.create(screen=screen, content=content)

    response = client.get(f"/api/screens/{screen.public_token}/config")

    item = response.json()["items"][0]
    assert item["injected_css"] == "body { display: none; }"
    assert item["injected_javascript_before"] == "window.before = true;"
    assert item["injected_javascript_after"] == "window.after = true;"


@pytest.mark.django_db
def test_screen_config_api_returns_internal_url_for_html_content(
    client, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    screen = Screen.objects.create(name="Lobby")
    content = Content.objects.create(html=HTML_CONTENT)
    ScreenContent.objects.create(screen=screen, content=content)

    response = client.get(f"/api/screens/{screen.public_token}/config")

    assert response.status_code == 200
    internal_path = f"/screens/{screen.public_token}/contents/{content.pk}/"
    assert response.json()["items"][0]["url"] == (
        response.wsgi_request.build_absolute_uri(internal_path)
    )


@pytest.mark.django_db
def test_html_content_endpoint_returns_uploaded_file(
    client, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    screen = Screen.objects.create(name="Lobby")
    content = Content.objects.create(html=HTML_CONTENT)
    ScreenContent.objects.create(screen=screen, content=content, order=1)
    ScreenContent.objects.create(screen=screen, content=content, order=2)

    response = client.get(
        reverse(
            "kiosks:content-content",
            args=[screen.public_token, content.pk],
        )
    )

    assert response.status_code == 200
    assert response["Content-Type"] == "text/html; charset=utf-8"
    assert response["Content-Security-Policy"].startswith("default-src 'none'")
    assert b"Embedded dashboard" in response.content


@pytest.mark.django_db
def test_media_content_uses_same_config_endpoint(client, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    screen = Screen.objects.create(name="Lobby")
    content = Content.objects.create(
        media=SimpleUploadedFile(
            "dashboard.png", b"image", content_type="image/png"
        )
    )
    ScreenContent.objects.create(screen=screen, content=content)

    response = client.get(f"/api/screens/{screen.public_token}/config")

    assert response.status_code == 200
    internal_path = f"/screens/{screen.public_token}/contents/{content.pk}/"
    assert response.json()["items"][0]["url"] == (
        response.wsgi_request.build_absolute_uri(internal_path)
    )


@pytest.mark.django_db
def test_image_content_endpoint_renders_centered_media_page(
    client, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    screen = Screen.objects.create(name="Lobby")
    content = Content.objects.create(
        label="Lobby image",
        media=SimpleUploadedFile(
            "dashboard.png", b"image", content_type="image/png"
        ),
    )
    ScreenContent.objects.create(screen=screen, content=content, order=1)
    ScreenContent.objects.create(screen=screen, content=content, order=2)

    response = client.get(
        reverse(
            "kiosks:content-content",
            args=[screen.public_token, content.pk],
        )
    )

    assert response.status_code == 200
    assert b"content-image" in response.content
    assert b"max-width: 100%" in response.content
    assert b"max-height: 100%" in response.content
    assert b"background: #000" in response.content
    assert response["Content-Security-Policy"].startswith("default-src 'none'")
    assert "img-src 'self'" in response["Content-Security-Policy"]


@pytest.mark.django_db
def test_video_content_endpoint_renders_muted_autoplay_player(
    client, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    screen = Screen.objects.create(name="Lobby")
    content = Content.objects.create(
        media=SimpleUploadedFile(
            "dashboard.mp4", b"video", content_type="video/mp4"
        )
    )
    ScreenContent.objects.create(screen=screen, content=content)

    response = client.get(
        reverse(
            "kiosks:content-content",
            args=[screen.public_token, content.pk],
        )
    )

    assert response.status_code == 200
    assert b"<video" in response.content
    assert b"autoplay" in response.content
    assert b"muted" in response.content
    assert b"playsinline" in response.content
    assert b"controls" not in response.content
    assert b'type="video/mp4"' in response.content
    assert "media-src 'self'" in response["Content-Security-Policy"]


@pytest.mark.django_db
def test_local_media_file_is_served(client):
    content = Content.objects.create(
        media=SimpleUploadedFile("dashboard.png", b"image")
    )
    try:
        response = client.get(content.media.url)
        body = b"".join(response.streaming_content)
    finally:
        content.delete()

    assert response.status_code == 200
    assert body == b"image"


@pytest.mark.django_db
def test_html_content_endpoint_hides_disabled_screen(
    client, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    screen = Screen.objects.create(name="Lobby", enabled=False)
    content = Content.objects.create(html=HTML_CONTENT)
    ScreenContent.objects.create(screen=screen, content=content)

    response = client.get(
        reverse(
            "kiosks:content-content",
            args=[screen.public_token, content.pk],
        )
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_runtime_status_api_persists_latest_snapshot(client):
    screen = Screen.objects.create(name="Lobby")
    content = Content.objects.create(url="https://example.com")
    ScreenContent.objects.create(screen=screen, content=content, order=1)
    ScreenContent.objects.create(screen=screen, content=content, order=2)

    response = client.post(
        f"/api/screens/{screen.public_token}/status",
        data=json.dumps(
            {
                "agent_version": "1.2.3",
                "browser_version": "Chromium 1",
                "uptime_seconds": 42,
                "health_state": "healthy",
                "current_content_id": content.pk,
                "desired_power_state": "on",
                "actual_power_state": "on",
                "display_identity": "HDMI-A-1",
                "display_width": 2560,
                "display_height": 1440,
                "display_refresh_rate": 59.95,
                "display_orientation": "normal",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    response_timestamp = datetime.fromisoformat(
        response.json()["last_check_in"].replace("Z", "+00:00")
    )
    assert response_timestamp.tzinfo == UTC
    screen.refresh_from_db()
    assert screen.status_agent_version == "1.2.3"
    assert screen.status_current_content_id == content.pk
    assert screen.status_uptime_seconds == 42
    assert screen.status_last_check_in is not None


@pytest.mark.django_db
def test_screenshot_api_keeps_newest_screen_content_image(
    client, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    screen = Screen.objects.create(name="Lobby")
    content = Content.objects.create(url="https://example.com")
    ScreenContent.objects.create(screen=screen, content=content, order=1)
    ScreenContent.objects.create(screen=screen, content=content, order=2)
    png = b"\x89PNG\r\n\x1a\nfirst"

    response = client.post(
        f"/api/screens/{screen.public_token}/screenshots",
        data={
            "content_id": str(content.pk),
            "captured_at": "2026-01-01T12:00:00Z",
            "health_state": "healthy",
            "image": SimpleUploadedFile(
                "first.png", png, content_type="image/png"
            ),
        },
    )
    assert response.status_code == 200
    assert response.json() == {"stored": True}

    response = client.post(
        f"/api/screens/{screen.public_token}/screenshots",
        data={
            "content_id": str(content.pk),
            "captured_at": "2026-01-01T11:00:00Z",
            "health_state": "error",
            "image": SimpleUploadedFile(
                "older.png", b"\x89PNG\r\n\x1a\nold", content_type="image/png"
            ),
        },
    )
    assert response.json() == {"stored": False}

    screen_content = ScreenContent.objects.filter(
        screen=screen, content=content
    ).order_by("pk").first()
    assert screen_content is not None
    assert screen_content.screenshot_health_state == "healthy"
    assert screen_content.screenshot_image.read() == png


@pytest.mark.django_db
def test_event_api_accepts_high_level_batch(client):
    screen = Screen.objects.create(name="Lobby")
    content = Content.objects.create(url="https://example.com/dashboard")
    ScreenContent.objects.create(screen=screen, content=content)

    response = client.post(
        f"/api/screens/{screen.public_token}/events",
        data=json.dumps(
            {
                "events": [
                    {
                        "code": "navigation_failed",
                        "level": "WARNING",
                        "message": "navigation failed",
                        "content_id": content.pk,
                        "url": "https://example.com/dashboard?token=secret",
                        "fingerprint": "navigation_failed:content",
                        "details": {"retry_count": 2},
                    },
                    {
                        "code": "agent_started",
                        "level": "INFO",
                        "message": "Agent started",
                    },
                    {
                        "code": "update_started",
                        "level": "INFO",
                        "message": "Updating agent",
                        "details": {
                            "from_version": "0.2.3",
                            "to_version": "0.2.4",
                        },
                    },
                ]
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json() == {"accepted": 3}
    event = Event.objects.get(code="navigation_failed")
    assert event.screen_id == screen.pk
    assert event.content_id == content.pk
    assert "token" not in event.url
    assert event.received_at is not None


@pytest.mark.django_db
def test_screen_config_api_returns_empty_playlist(client):
    screen = Screen.objects.create(name="Lobby")

    response = client.get(f"/api/screens/{screen.public_token}/config")

    assert response.status_code == 200
    assert response.json()["items"] == []


@pytest.mark.django_db
def test_screen_config_api_hides_disabled_screens(client):
    screen = Screen.objects.create(name="Lobby", enabled=False)

    response = client.get(f"/api/screens/{screen.public_token}/config")

    assert response.status_code == 404


@pytest.mark.django_db
def test_screen_page_renders_config_endpoint(client):
    screen = Screen.objects.create(name="Lobby")

    response = client.get(
        reverse("kiosks:screen-display", args=[screen.public_token])
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Lobby" in content
    assert f"/api/screens/{screen.public_token}/config" in content


@pytest.mark.django_db
def test_rotated_token_invalidates_old_screen_urls(client):
    screen = Screen.objects.create(name="Lobby")
    old_token = screen.public_token

    screen.rotate_public_token()

    old_response = client.get(f"/api/screens/{old_token}/config")
    new_response = client.get(f"/api/screens/{screen.public_token}/config")

    assert old_response.status_code == 404
    assert new_response.status_code == 200
