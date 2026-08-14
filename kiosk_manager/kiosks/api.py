from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from ninja import Router, Schema

from .models import Screen
from .services import get_screen_configuration

router = Router(tags=["screens"])


class ScreenURLOutput(Schema):
    url: str
    duration_seconds: int
    order: int


class ScreenConfigurationOutput(Schema):
    version: str
    items: list[ScreenURLOutput]


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
        "items": [
            {
                "url": str(item.url),
                "duration_seconds": item.duration_seconds,
                "order": item.order,
            }
            for item in items
        ],
    }
