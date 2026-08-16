from datetime import UTC, datetime

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

import pytest
from recurrence import DAILY, Recurrence, Rule

from kiosk_manager.kiosks.models import (
    Content,
    Screen,
    ScreenCommand,
    ScreenContent,
)
from kiosk_manager.kiosks.services import get_screen_configuration


@pytest.mark.django_db
def test_screen_generates_public_token():
    screen = Screen.objects.create(name="Lobby")

    assert screen.public_token
    assert len(screen.public_token) >= 32


def test_screen_get_absolute_url():
    screen = Screen(name="Lobby")

    assert screen.get_absolute_url() == f"/screens/{screen.public_token}/"


@pytest.mark.django_db
def test_screen_rotates_public_token():
    screen = Screen.objects.create(name="Lobby")
    old_token = screen.public_token

    screen.rotate_public_token()
    screen.refresh_from_db()

    assert screen.public_token != old_token


@pytest.mark.django_db
def test_playlist_is_ordered_and_configuration_has_version():
    screen = Screen.objects.create(name="Lobby")
    second_content = Content.objects.create(url="https://example.com/second")
    first_content = Content.objects.create(url="https://example.com/first")
    second = ScreenContent.objects.create(
        screen=screen,
        content=second_content,
        duration_seconds=20,
        order=2,
    )
    first = ScreenContent.objects.create(
        screen=screen,
        content=first_content,
        duration_seconds=10,
        order=1,
    )

    version, items = get_screen_configuration(screen)

    assert version
    assert items == [first, second]


@pytest.mark.django_db
def test_configuration_version_changes_when_injection_changes():
    screen = Screen.objects.create(name="Lobby")
    content = Content.objects.create(url="https://example.com")
    ScreenContent.objects.create(screen=screen, content=content)

    original_version, _items = get_screen_configuration(screen)
    content.injected_css = ".public-dashboard-footer { display: none; }"
    content.save(update_fields=["injected_css"])

    updated_version, _items = get_screen_configuration(screen)

    assert updated_version != original_version


@pytest.mark.django_db
@pytest.mark.django_db
def test_configuration_version_changes_when_source_changes():
    screen = Screen.objects.create(name="Lobby")
    content = Content.objects.create(url="https://example.com")
    ScreenContent.objects.create(screen=screen, content=content)

    original_version, _items = get_screen_configuration(screen)
    content.url = ""
    content.media = SimpleUploadedFile("image.png", b"image")
    content.save()

    updated_version, _items = get_screen_configuration(screen)

    assert updated_version != original_version


@pytest.mark.django_db
def test_content_label_is_used_for_string_representation():
    content = Content(label="Lobby dashboard", url="https://example.com")

    assert str(content) == "Lobby dashboard"


@pytest.mark.django_db
def test_content_requires_single_source():
    with pytest.raises(ValidationError):
        Content().full_clean()
    with pytest.raises(ValidationError):
        Content(
            url="https://example.com",
            html="<h1>Hello</h1>",
        ).full_clean()

    content = Content(label="Uploaded content", html="<h1>Hello</h1>")
    content.full_clean()
    assert content.html == "<h1>Hello</h1>"


@pytest.mark.django_db
def test_content_rejects_unsupported_media_upload():
    content = Content(
        media=SimpleUploadedFile("page.txt", b"hello"),
    )

    with pytest.raises(ValidationError):
        content.full_clean()


@pytest.mark.django_db
@pytest.mark.parametrize("value", [-1, "-1"])
def test_content_rejects_invalid_preload_delay(value):
    content = Content(
        url="https://example.com",
        preload_delay_seconds=value,
    )

    with pytest.raises(ValidationError):
        content.full_clean()


@pytest.mark.django_db
def test_playlist_entry_requires_positive_duration():
    screen = Screen.objects.create(name="Lobby")
    content = Content.objects.create(url="https://example.com")
    entry = ScreenContent(
        screen=screen,
        content=content,
        duration_seconds=0,
        order=1,
    )

    with pytest.raises(ValidationError):
        entry.full_clean()


@pytest.mark.django_db
def test_playlist_order_is_unique_per_screen():
    screen = Screen.objects.create(name="Lobby")
    first = Content.objects.create(url="https://example.com/first")
    second = Content.objects.create(url="https://example.com/second")
    ScreenContent.objects.create(screen=screen, content=first, order=1)

    with pytest.raises(ValidationError):
        ScreenContent(
            screen=screen,
            content=second,
            order=1,
        ).validate_constraints()


@pytest.mark.django_db
def test_same_content_can_repeat_in_playlist():
    screen = Screen.objects.create(name="Lobby")
    content = Content.objects.create(url="https://example.com")

    ScreenContent.objects.create(screen=screen, content=content, order=1)
    ScreenContent.objects.create(screen=screen, content=content, order=2)

    assert screen.playlist_entries.count() == 2


@pytest.mark.django_db
def test_desired_power_state_defaults_on_without_schedule():
    screen = Screen.objects.create(name="Lobby")

    assert screen.desired_power_state() == "on"


@pytest.mark.django_db
def test_power_override_takes_precedence_over_schedule():
    screen = Screen.objects.create(
        name="Lobby",
        on_schedule=(
            "DTSTART:20260101T000000Z\n"
            "RRULE:FREQ=DAILY;BYHOUR=8;BYMINUTE=0;BYSECOND=0"
        ),
        off_schedule=(
            "DTSTART:20260101T000000Z\n"
            "RRULE:FREQ=DAILY;BYHOUR=22;BYMINUTE=0;BYSECOND=0"
        ),
    )
    at = datetime(2026, 1, 2, 23, tzinfo=UTC)

    assert screen.scheduled_power_state(at) == "off"
    screen.power_override = "on"

    assert screen.desired_power_state(at) == "on"


@pytest.mark.django_db
def test_scheduled_power_state_anchors_rules_without_dtstart():
    screen = Screen(
        name="Lobby",
        on_schedule="RRULE:FREQ=DAILY;BYHOUR=8;BYMINUTE=0;BYSECOND=0",
    )

    assert (
        screen.scheduled_power_state(datetime(2026, 1, 2, 9, tzinfo=UTC))
        == "on"
    )


@pytest.mark.django_db
def test_scheduled_power_state_normalizes_naive_recurrence_occurrences():
    screen = Screen(
        name="Lobby",
        on_schedule=Recurrence(
            dtstart=datetime(2026, 1, 1, 8),
            rrules=[Rule(DAILY)],
        ),
    )

    assert (
        screen.scheduled_power_state(datetime(2026, 1, 2, 9, tzinfo=UTC))
        == "on"
    )


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
