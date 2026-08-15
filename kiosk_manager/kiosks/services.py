import hashlib
import json
from typing import cast

from django.conf import settings

from .models import Page, Screen


def effective_preload_delay_seconds(screen: Screen, page: Page) -> float:
    value = (
        page.preload_delay_seconds
        if page.preload_delay_seconds is not None
        else screen.preload_delay_seconds
    )
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("invalid preload delay") from exc


def effective_preload_timeout_seconds(screen: Screen, page: Page) -> int:
    return (
        page.preload_timeout_seconds
        if page.preload_timeout_seconds is not None
        else screen.preload_timeout_seconds
    )


def page_url(screen: Screen, page: Page) -> str:
    if page.html_file:
        return (
            f"{settings.SITE_BASE_PATH}/screens/{screen.public_token}/"
            f"pages/{page.pk}/"
        )
    return str(page.url)


def serialize_schedule(schedule) -> str | None:
    value = str(schedule or "")
    return value or None


def power_status(screen: Screen) -> dict:
    pending = screen.pending_command()
    return {
        "power_override": screen.power_override or None,
        "desired_power_state": screen.desired_power_state(),
        "reported_power_state": screen.reported_power_state,
        "reported_power_at": screen.reported_power_at,
        "pending_command": (
            {"id": pending.id, "command": pending.command}
            if pending is not None
            else None
        ),
    }


def get_screen_configuration(screen: Screen):
    items = list(Page.objects.filter(screen=screen).order_by("order", "pk"))
    version_payload = [
        {
            "url": page_url(screen, item),
            "duration_seconds": cast(int, item.duration_seconds),
            "order": cast(int, item.order),
            "preload_delay_seconds": effective_preload_delay_seconds(
                screen, item
            ),
            "preload_timeout_seconds": effective_preload_timeout_seconds(
                screen, item
            ),
        }
        for item in items
    ]
    version_payload.extend(
        [
            {"on_schedule": serialize_schedule(screen.on_schedule)},
            {"off_schedule": serialize_schedule(screen.off_schedule)},
        ]
    )
    version = hashlib.sha256(
        json.dumps(
            version_payload,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return version, items
