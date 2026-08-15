from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from ninja import Router, Schema

from .models import Screen
from .services import (
    effective_preload_delay_seconds,
    effective_preload_timeout_seconds,
    get_screen_configuration,
    page_url,
    serialize_schedule,
)

router = Router(tags=["screens"])


class PageOutput(Schema):
    url: str
    duration_seconds: int
    order: int
    preload_delay_seconds: float
    preload_timeout_seconds: int


class ScreenConfigurationOutput(Schema):
    version: str
    items: list[PageOutput]
    on_schedule: str | None
    off_schedule: str | None


@router.get(
    "/screens/{token}/config",
    response=ScreenConfigurationOutput,
)
def get_screen_config(request, token: str, response: HttpResponse):
    screen = get_object_or_404(
        Screen.objects.all(),
        public_token=token,
        enabled=True,
    )
    version, items = get_screen_configuration(screen)
    response["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return {
        "version": version,
        "on_schedule": serialize_schedule(screen.on_schedule),
        "off_schedule": serialize_schedule(screen.off_schedule),
        "items": [
            {
                "url": page_url(screen, item),
                "duration_seconds": item.duration_seconds,
                "order": item.order,
                "preload_delay_seconds": effective_preload_delay_seconds(
                    screen, item
                ),
                "preload_timeout_seconds": (
                    effective_preload_timeout_seconds(screen, item)
                ),
            }
            for item in items
        ],
    }
