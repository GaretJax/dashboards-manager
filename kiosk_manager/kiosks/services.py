import hashlib
import json
from datetime import UTC, datetime
from typing import cast

from django.conf import settings
from django.utils import timezone

from .models import Content, Screen, ScreenContent


def utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if timezone.is_naive(value):
        value = timezone.make_aware(value)
    return value.astimezone(UTC)


def effective_preload_delay_seconds(content: Content) -> float:
    try:
        return float(content.preload_delay_seconds)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("invalid preload delay") from exc


def effective_preload_timeout_seconds(content: Content) -> int:
    return cast(int, content.preload_timeout_seconds)


def content_url(screen: Screen, content: Content) -> str:
    if content.html or content.media:
        return (
            f"{settings.SITE_BASE_PATH}/screens/{screen.public_token}/"
            f"contents/{content.pk}/"
        )
    return str(content.url)


def serialize_schedule(schedule) -> str | None:
    value = str(schedule or "")
    return value or None


def power_status(screen: Screen) -> dict:
    pending = screen.pending_command()
    return {
        "desired_power_state": screen.desired_power_state(),
        "reported_power_state": screen.status_power_state,
        "reported_power_at": utc_datetime(screen.status_power_at),
        "pending_command": (
            {"id": pending.id, "command": pending.command}
            if pending is not None
            else None
        ),
    }


def get_screen_configuration(screen: Screen):
    entries = list(
        ScreenContent.objects.filter(screen=screen)
        .select_related("content")
        .order_by("order", "pk")
    )
    version_payload = [
        {
            "content_id": entry.content_id,
            "url": content_url(screen, entry.content),
            "duration_seconds": cast(int, entry.duration_seconds),
            "order": cast(int, entry.order),
            "preload_delay_seconds": effective_preload_delay_seconds(
                entry.content
            ),
            "preload_timeout_seconds": effective_preload_timeout_seconds(
                entry.content
            ),
            "html_hash": hashlib.sha256(
                entry.content.html.encode("utf-8")
            ).hexdigest(),
            "media_name": entry.content.media.name or "",
            "source_updated_at": entry.content.updated_at.isoformat(),
            "injected_css": entry.content.injected_css or "",
            "injected_javascript_before": (
                entry.content.injected_javascript_before or ""
            ),
            "injected_javascript_after": (
                entry.content.injected_javascript_after or ""
            ),
        }
        for entry in entries
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
    return version, entries
