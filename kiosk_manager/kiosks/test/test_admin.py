from django.urls import reverse

import pytest

from kiosk_manager.kiosks.admin.screen import ScreenAdmin
from kiosk_manager.kiosks.models import Screen


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
        "PUBLIC ACCESS",
        "AGENT INSTALLATION",
        "TIMESTAMPS",
    ]


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
def test_screen_admin_restart_action_is_idempotent(admin_client):
    screen = Screen.objects.create(name="Lobby")
    action_url = reverse(
        "admin:kiosks_screen_actions",
        kwargs={"pk": screen.pk, "tool": "restart_agent_action"},
    )

    admin_client.post(action_url)
    admin_client.post(action_url)

    assert screen.commands.count() == 1
