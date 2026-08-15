import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

import pytest

from kiosk_manager.kiosks.models import Page, Screen


def _html_file():
    return SimpleUploadedFile(
        "dashboard.html",
        b"<!doctype html><h1>Embedded dashboard</h1>",
        content_type="text/html",
    )


@pytest.mark.django_db
def test_screen_config_api_returns_ordered_pages(client):
    screen = Screen.objects.create(name="Lobby")
    Page.objects.create(
        screen=screen,
        url="https://example.com/second",
        duration_seconds=20,
        order=2,
    )
    Page.objects.create(
        screen=screen,
        url="https://example.com/first",
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
            "url": "https://example.com/first",
            "duration_seconds": 10,
            "order": 1,
            "preload_delay_seconds": 0.0,
            "preload_timeout_seconds": 30,
        },
        {
            "url": "https://example.com/second",
            "duration_seconds": 20,
            "order": 2,
            "preload_delay_seconds": 0.0,
            "preload_timeout_seconds": 30,
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
def test_screen_config_api_applies_page_preload_overrides(client):
    screen = Screen.objects.create(
        name="Lobby",
        preload_delay_seconds=4,
        preload_timeout_seconds=45,
    )
    Page.objects.create(
        screen=screen,
        url="https://example.com/inherit",
        order=1,
    )
    Page.objects.create(
        screen=screen,
        url="https://example.com/override",
        order=2,
        preload_delay_seconds=2.5,
        preload_timeout_seconds=10,
    )

    response = client.get(f"/api/screens/{screen.public_token}/config")

    assert response.json()["items"] == [
        {
            "url": "https://example.com/inherit",
            "duration_seconds": 30,
            "order": 1,
            "preload_delay_seconds": 4.0,
            "preload_timeout_seconds": 45,
        },
        {
            "url": "https://example.com/override",
            "duration_seconds": 30,
            "order": 2,
            "preload_delay_seconds": 2.5,
            "preload_timeout_seconds": 10,
        },
    ]


@pytest.mark.django_db
def test_screen_config_api_returns_internal_url_for_html_page(
    client, settings, tmp_path
):
    settings.MEDIA_ROOT = tmp_path
    screen = Screen.objects.create(name="Lobby")
    page = Page.objects.create(screen=screen, html_file=_html_file())

    response = client.get(f"/api/screens/{screen.public_token}/config")

    assert response.status_code == 200
    assert response.json()["items"][0]["url"] == (
        f"/screens/{screen.public_token}/pages/{page.pk}/"
    )


@pytest.mark.django_db
def test_html_page_endpoint_returns_uploaded_file(client, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    screen = Screen.objects.create(name="Lobby")
    page = Page.objects.create(screen=screen, html_file=_html_file())

    response = client.get(
        reverse(
            "kiosks:page-content",
            args=[screen.public_token, page.pk],
        )
    )

    assert response.status_code == 200
    assert response["Content-Type"] == "text/html; charset=utf-8"
    assert response["Content-Security-Policy"].startswith("default-src 'none'")
    assert b"Embedded dashboard" in response.content


@pytest.mark.django_db
def test_html_page_endpoint_hides_disabled_screen(client, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    screen = Screen.objects.create(name="Lobby", enabled=False)
    page = Page.objects.create(screen=screen, html_file=_html_file())

    response = client.get(
        reverse("kiosks:page-content", args=[screen.public_token, page.pk])
    )

    assert response.status_code == 404


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
