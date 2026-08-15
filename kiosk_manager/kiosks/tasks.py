from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from celery import shared_task

from .models import Event


@shared_task(ignore_result=True)
def delete_expired_events():
    cutoff = timezone.now() - timedelta(days=settings.EVENT_RETENTION_DAYS)
    deleted, _details = Event.objects.filter(received_at__lt=cutoff).delete()
    return deleted
