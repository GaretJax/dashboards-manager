from datetime import UTC, datetime

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

import pytest

from kiosk_manager.kiosks.models import Page, Screen, ScreenCommand
from kiosk_manager.kiosks.services import get_screen_configuration


def _page_file(name="page.html", content=b"<h1>Hello</h1>"):
    return SimpleUploadedFile(name, content, content_type="text/html")


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
def test_pages_are_ordered_and_configuration_has_version():
    screen = Screen.objects.create(name="Lobby")
    second = Page.objects.create(
        screen=screen,
        url="https://example.com/second",
        duration_seconds=20,
        order=2,
    )
    first = Page.objects.create(
        screen=screen,
        url="https://example.com/first",
        duration_seconds=10,
        order=1,
    )

    version, items = get_screen_configuration(screen)

    assert version
    assert items == [first, second]


@pytest.mark.django_db
def test_page_requires_url_xor_html_file():
    screen = Screen.objects.create(name="Lobby")

    with pytest.raises(ValidationError):
        Page(screen=screen, order=1).full_clean()
    with pytest.raises(ValidationError):
        Page(
            screen=screen,
            url="https://example.com",
            html_file=_page_file(),
            order=1,
        ).full_clean()

    page = Page(screen=screen, html_file=_page_file(), order=1)
    page.full_clean()
    assert page.html_file.name == "page.html"


@pytest.mark.django_db
def test_page_rejects_non_html_upload():
    screen = Screen.objects.create(name="Lobby")
    page = Page(
        screen=screen,
        html_file=SimpleUploadedFile("page.txt", b"hello"),
    )

    with pytest.raises(ValidationError):
        page.full_clean()


@pytest.mark.django_db
@pytest.mark.parametrize("value", [-1, "-1"])
def test_page_rejects_invalid_preload_delay(value):
    screen = Screen.objects.create(name="Lobby")
    page = Page(
        screen=screen,
        url="https://example.com",
        preload_delay_seconds=value,
    )

    with pytest.raises(ValidationError):
        page.full_clean()


@pytest.mark.django_db
def test_page_requires_positive_duration():
    screen = Screen.objects.create(name="Lobby")
    page = Page(
        screen=screen,
        url="https://example.com",
        duration_seconds=0,
        order=1,
    )

    with pytest.raises(ValidationError):
        page.full_clean()


@pytest.mark.django_db
def test_page_order_is_unique_per_screen():
    screen = Screen.objects.create(name="Lobby")
    Page.objects.create(
        screen=screen,
        url="https://example.com/first",
        order=1,
    )

    with pytest.raises(ValidationError):
        Page(
            screen=screen,
            url="https://example.com/second",
            order=1,
        ).validate_constraints()


@pytest.mark.django_db
def test_power_override_takes_precedence_over_schedule():
    screen = Screen.objects.create(
        name="Lobby",
        on_schedule="DTSTART:20260101T080000Z\nRRULE:FREQ=DAILY",
        off_schedule="DTSTART:20260101T220000Z\nRRULE:FREQ=DAILY",
    )
    at = datetime(2026, 1, 2, 23, tzinfo=UTC)

    assert screen.scheduled_power_state(at) == "off"
    screen.power_override = "on"

    assert screen.desired_power_state(at) == "on"


@pytest.mark.django_db
def test_restart_command_is_idempotent_until_acknowledged():
    screen = Screen.objects.create(name="Lobby")

    first = screen.request_agent_restart()
    second = screen.request_agent_restart()

    assert first.pk == second.pk
    assert ScreenCommand.objects.filter(screen=screen).count() == 1

    first.acknowledged_at = datetime.now(UTC)
    first.save(update_fields=["acknowledged_at"])
    third = screen.request_agent_restart()

    assert third.pk != first.pk
    assert ScreenCommand.objects.filter(screen=screen).count() == 2
