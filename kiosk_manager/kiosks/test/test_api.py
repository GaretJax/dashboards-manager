from django.urls import reverse

import pytest

from kiosk_manager.kiosks.models import Screen, ScreenURL


@pytest.mark.django_db
def test_screen_config_api_returns_ordered_urls(client):
    screen = Screen.objects.create(name="Lobby")
    ScreenURL.objects.create(
        screen=screen,
        url="https://example.com/second",
        duration_seconds=20,
        order=2,
    )
    ScreenURL.objects.create(
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
    assert payload["items"] == [
        {
            "url": "https://example.com/first",
            "duration_seconds": 10,
            "order": 1,
        },
        {
            "url": "https://example.com/second",
            "duration_seconds": 20,
            "order": 2,
        },
    ]


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
