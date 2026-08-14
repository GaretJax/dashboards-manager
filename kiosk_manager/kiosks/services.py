import hashlib
import json
from typing import cast

from .models import Screen, ScreenURL


def get_screen_configuration(screen: Screen):
    items = list(
        ScreenURL.objects.filter(screen=screen).order_by("order", "pk")
    )
    version_payload = [
        {
            "url": str(item.url),
            "duration_seconds": cast(int, item.duration_seconds),
            "order": cast(int, item.order),
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
