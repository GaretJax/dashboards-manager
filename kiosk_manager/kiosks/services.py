import hashlib
import json
from typing import cast

from .models import (
    Screen,
    ScreenURL,
    serialize_preload_seconds,
)


def effective_preload_seconds(screen: Screen, item: ScreenURL):
    value = item.preload_seconds or screen.preload_seconds
    return serialize_preload_seconds(value)


def effective_preload_timeout_seconds(screen: Screen, item: ScreenURL):
    return (
        item.preload_timeout_seconds
        if item.preload_timeout_seconds is not None
        else screen.preload_timeout_seconds
    )


def get_screen_configuration(screen: Screen):
    items = list(
        ScreenURL.objects.filter(screen=screen).order_by("order", "pk")
    )
    version_payload = [
        {
            "url": str(item.url),
            "duration_seconds": cast(int, item.duration_seconds),
            "order": cast(int, item.order),
            "preload_seconds": effective_preload_seconds(screen, item),
            "preload_timeout_seconds": effective_preload_timeout_seconds(
                screen, item
            ),
        }
        for item in items
    ]
    version = hashlib.sha256(
        json.dumps(
            version_payload,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return version, items
