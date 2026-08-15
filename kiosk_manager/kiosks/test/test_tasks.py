from datetime import timedelta

from django.utils import timezone

import pytest

from kiosk_manager.kiosks.models import Event, Screen
from kiosk_manager.kiosks.tasks import delete_expired_events


@pytest.mark.django_db
def test_delete_expired_events_retains_recent_events(settings):
    settings.EVENT_RETENTION_DAYS = 30
    screen = Screen.objects.create(name="Lobby")
    expired = Event.objects.create(
        screen=screen,
        code="navigation_failed",
        level="WARNING",
        message="old",
        occurred_at=timezone.now(),
    )
    recent = Event.objects.create(
        screen=screen,
        code="page_loaded",
        level="INFO",
        message="new",
        occurred_at=timezone.now(),
    )
    Event.objects.filter(pk=expired.pk).update(
        received_at=timezone.now() - timedelta(days=31)
    )

    delete_expired_events()

    assert not Event.objects.filter(pk=expired.pk).exists()
    assert Event.objects.filter(pk=recent.pk).exists()
