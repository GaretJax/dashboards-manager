from django.core.exceptions import ValidationError

import pytest

from kiosk_manager.kiosks.models import Screen, ScreenURL
from kiosk_manager.kiosks.services import get_screen_configuration


@pytest.mark.django_db
def test_screen_generates_public_token():
    screen = Screen.objects.create(name="Lobby")

    assert screen.public_token
    assert len(screen.public_token) >= 32


@pytest.mark.django_db
def test_screen_rotates_public_token():
    screen = Screen.objects.create(name="Lobby")
    old_token = screen.public_token

    screen.rotate_public_token()
    screen.refresh_from_db()

    assert screen.public_token != old_token


@pytest.mark.django_db
def test_screen_urls_are_ordered_and_configuration_has_version():
    screen = Screen.objects.create(name="Lobby")
    second = ScreenURL.objects.create(
        screen=screen,
        url="https://example.com/second",
        duration_seconds=20,
        order=2,
    )
    first = ScreenURL.objects.create(
        screen=screen,
        url="https://example.com/first",
        duration_seconds=10,
        order=1,
    )

    version, items = get_screen_configuration(screen)

    assert version
    assert items == [first, second]


@pytest.mark.django_db
def test_screen_url_requires_positive_duration():
    screen = Screen.objects.create(name="Lobby")
    item = ScreenURL(
        screen=screen,
        url="https://example.com",
        duration_seconds=0,
        order=1,
    )

    with pytest.raises(ValidationError):
        item.full_clean()


@pytest.mark.django_db
def test_screen_url_order_is_unique_per_screen():
    screen = Screen.objects.create(name="Lobby")
    ScreenURL.objects.create(
        screen=screen,
        url="https://example.com/first",
        order=1,
    )

    with pytest.raises(ValidationError):
        ScreenURL(
            screen=screen,
            url="https://example.com/second",
            order=1,
        ).validate_constraints()
