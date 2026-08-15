import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

import pytest

from kiosk_manager.kiosks.models import (
    Content,
    Screen,
    ScreenContent,
    ScreenContentScreenshot,
    ScreenRuntimeStatus,
)


def _html_file():
    return SimpleUploadedFile(
        "dashboard.html",
        b"<!doctype html><h1>Embedded dashboard</h1>",
        content_type="text/html",
    )


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
    assert payload["on_schedule"] is None
    assert payload["off_schedule"] is None
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
    assert payload["power_override"] is None
    assert payload["desired_power_state"] is None
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
    assert payload["pending_command"] is None
    command.refresh_from_db()
    assert command.acknowledged_at is not None


@pytest.mark.django_db
def test_screen_config_api_returns_power_schedules(client):
    screen = Screen.objects.create(
        name="Lobby",
        on_schedule="DTSTART:20260101T080000Z\nRRULE:FREQ=DAILY",
        off_schedule="DTSTART:20260101T220000Z\nRRULE:FREQ=DAILY",
    )

    response = client.get(f"/api/screens/{screen.public_token}/config")

    payload = response.json()
    assert payload["on_schedule"] == (
        "DTSTART:20260101T080000Z\nRRULE:FREQ=DAILY"
    )
    assert payload["off_schedule"] == (
        "DTSTART:20260101T220000Z\nRRULE:FREQ=DAILY"
    )


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
    content = Content.objects.create(html_file=_html_file())
    ScreenContent.objects.create(screen=screen, content=content)

    response = client.get(f"/api/screens/{screen.public_token}/config")

    assert response.status_code == 200
    assert response.json()["items"][0]["url"] == (
        f"/screens/{screen.public_token}/contents/{content.pk}/"
    )


@pytest.mark.django_db
def test_html_content_endpoint_returns_uploaded_file(
    client, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    screen = Screen.objects.create(name="Lobby")
    content = Content.objects.create(html_file=_html_file())
    ScreenContent.objects.create(screen=screen, content=content)

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
def test_html_content_endpoint_hides_disabled_screen(
    client, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    screen = Screen.objects.create(name="Lobby", enabled=False)
    content = Content.objects.create(html_file=_html_file())
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
    ScreenContent.objects.create(screen=screen, content=content)

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
    status = ScreenRuntimeStatus.objects.get(screen=screen)
    assert status.agent_version == "1.2.3"
    assert status.current_content_id == content.pk
    assert status.last_check_in is not None


@pytest.mark.django_db
def test_screenshot_api_keeps_newest_screen_content_image(
    client, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    screen = Screen.objects.create(name="Lobby")
    content = Content.objects.create(url="https://example.com")
    ScreenContent.objects.create(screen=screen, content=content)
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

    screenshot = ScreenContentScreenshot.objects.get(
        screen=screen, content=content
    )
    assert screenshot.health_state == "healthy"
    assert screenshot.image.read() == png


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
