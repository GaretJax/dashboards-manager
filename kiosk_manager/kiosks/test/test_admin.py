from django.urls import reverse

import pytest

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
