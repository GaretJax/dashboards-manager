import logging
import os

from celery import Celery
from celery.signals import task_failure, task_postrun, task_prerun

logger = logging.getLogger(__name__)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "kiosk_manager.settings")

app = Celery("kiosk_manager")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@task_prerun.connect(weak=False)
def log_task_started(task_id, task, **kwargs):
    del kwargs
    logger.info("Celery task started: %s[%s]", task.name, task_id)


@task_postrun.connect(weak=False)
def log_task_finished(task_id, task, state, **kwargs):
    del kwargs
    logger.info(
        "Celery task finished: %s[%s] state=%s", task.name, task_id, state
    )


@task_failure.connect(weak=False)
def log_task_failed(task_id, exception, sender, **kwargs):
    del kwargs
    logger.error(
        "Celery task failed: %s[%s]: %s",
        sender.name,
        task_id,
        exception,
    )
