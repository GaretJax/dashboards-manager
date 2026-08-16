from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

import pytest

from kiosk_manager.kiosks.admin.runtime import (
    ScreenContentScreenshotAdmin,
    ScreenRuntimeStatusAdmin,
)
from kiosk_manager.kiosks.admin.screen import ScreenAdmin
from kiosk_manager.kiosks.forms import ScreenAdminForm
from kiosk_manager.kiosks.models import Screen, ScreenCommand


@pytest.mark.django_db
def test_screen_admin_exposes_rotate_token_detail_action(admin_client):
    screen = Screen.objects.create(name="Lobby")
    old_token = screen.public_token
    action_url = reverse(
        "admin:kiosks_screen_actions",
        kwargs={
            "pk": screen.pk,
            "tool": "rotate_public_token_action",
        },
    )

    response = admin_client.post(action_url)

    screen.refresh_from_db()
    assert response.status_code == 302
    assert screen.public_token != old_token
    assert [title for title, _options in ScreenAdmin.fieldsets] == [
        "SCREEN",
        "POWER SCHEDULE",
        "REMOTE STATE",
        "AGENT INSTALLATION",
        "TIMESTAMPS",
    ]


def test_runtime_admin_disables_manual_additions():
    assert not ScreenRuntimeStatusAdmin.has_add_permission(None, None)
    assert not ScreenContentScreenshotAdmin.has_add_permission(None, None)


def test_screen_admin_schedule_widget_includes_time_control():
    form = ScreenAdminForm()

    assert form.fields["on_schedule"].widget.__class__.__name__ == (
        "ScheduleRecurrenceWidget"
    )
    assert "kiosks/recurrence-time.js" in "".join(form.media.render_js())


def test_screen_admin_power_states_use_boolean_icons_and_override_label():
    screen = Screen(
        power_override="on",
        reported_power_state="off",
        reported_power_at=timezone.now(),
    )

    desired = ScreenAdmin.desired_power_state_display(None, screen)
    reported = ScreenAdmin.reported_power_state_display(None, screen)

    assert "icon-yes.svg" in str(desired)
    assert "overridden" in str(desired)
    assert "icon-no.svg" in str(reported)
    assert "last reported at:" in str(reported)


@pytest.mark.django_db
def test_screen_admin_desired_state_shows_next_scheduled_change():
    screen = Screen.objects.create(
        name="Lobby",
        on_schedule="RRULE:FREQ=DAILY;BYHOUR=0;BYMINUTE=0;BYSECOND=0",
        off_schedule="RRULE:FREQ=DAILY;BYHOUR=23;BYMINUTE=59;BYSECOND=0",
    )

    desired = ScreenAdmin.desired_power_state_display(None, screen)

    assert "next change:" in str(desired)


def test_screen_admin_unknown_power_state_uses_unknown_icon():
    screen = Screen(reported_power_state="unknown")

    reported = ScreenAdmin.reported_power_state_display(None, screen)

    assert "icon-unknown.svg" in str(reported)


@pytest.mark.django_db
def test_screen_admin_shows_agent_install_command(admin_client):
    screen = Screen.objects.create(name="Lobby")

    response = admin_client.get(
        reverse(
            "admin:kiosks_screen_change",
            kwargs={"object_id": screen.pk},
        )
    )

    assert response.status_code == 200
    assert f"install.sh?screen={screen.public_token}" in response.text
    assert "View on site" in response.text
    assert "curl -fsSL" in response.text


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("tool", "expected_override"),
    [
        ("screen_on_action", "on"),
        ("screen_off_action", "off"),
        ("follow_schedule_action", ""),
    ],
)
def test_screen_admin_power_actions(admin_client, tool, expected_override):
    screen = Screen.objects.create(name="Lobby", power_override="off")

    response = admin_client.post(
        reverse(
            "admin:kiosks_screen_actions",
            kwargs={"pk": screen.pk, "tool": tool},
        )
    )

    screen.refresh_from_db()
    assert response.status_code == 302
    assert screen.power_override == expected_override


@pytest.mark.django_db
def test_screen_admin_clears_all_pending_commands(admin_client):
    screen = Screen.objects.create(name="Lobby")
    ScreenCommand.objects.create(screen=screen, command="restart_agent")

    response = admin_client.post(
        reverse(
            "admin:kiosks_screen_actions",
            kwargs={
                "pk": screen.pk,
                "tool": "clear_pending_commands_action",
            },
        )
    )

    assert response.status_code == 302
    assert not screen.commands.filter(acknowledged_at__isnull=True).exists()
    assert ScreenAdmin.pending_agent_command_display(None, screen) == "-"


@pytest.mark.django_db
def test_screen_admin_pending_command_shows_metadata_as_code(admin_client):
    screen = Screen.objects.create(name="Lobby")
    command = ScreenCommand.objects.create(
        screen=screen,
        command="restart_agent",
        created_by=get_user_model().objects.get(username="admin"),
    )

    display = ScreenAdmin.pending_agent_command_display(None, screen)

    assert "<code>restart_agent</code>" in str(display)
    assert "created at:" in str(display)
    assert "by: admin" in str(display)
    assert command.acknowledged_at is None


@pytest.mark.django_db
def test_screen_admin_restart_action_is_idempotent(admin_client):
    screen = Screen.objects.create(name="Lobby")
    action_url = reverse(
        "admin:kiosks_screen_actions",
        kwargs={"pk": screen.pk, "tool": "restart_agent_action"},
    )

    admin_client.post(action_url)
    admin_client.post(action_url)

    assert screen.commands.count() == 1
    assert screen.commands.get().created_by.username == "admin"
