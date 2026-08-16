import math
import re
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from django.core.files.storage import default_storage
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from ninja import Router, Schema
from ninja.errors import HttpError

from .models import (
    Content,
    Event,
    EventLevel,
    HealthState,
    PowerState,
    Screen,
    ScreenContentScreenshot,
    ScreenRuntimeStatus,
)
from .services import (
    content_url,
    effective_preload_delay_seconds,
    effective_preload_timeout_seconds,
    get_screen_configuration,
    power_status,
    utc_datetime,
)

router = Router(tags=["screens"])
EVENT_DETAIL_KEYS = {
    "browser_target",
    "current_version",
    "display_identity",
    "error",
    "phase",
    "recovered",
    "remote_version",
    "retry_count",
    "stage",
    "state",
    "wheel_filename",
}


class PlaylistItemOutput(Schema):
    content_id: int
    url: str
    duration_seconds: int
    order: int
    preload_delay_seconds: float
    preload_timeout_seconds: int
    injected_css: str | None
    injected_javascript_before: str | None
    injected_javascript_after: str | None


class PendingCommandOutput(Schema):
    id: UUID
    command: str


class PowerStatusOutput(Schema):
    desired_power_state: str | None
    reported_power_state: str
    reported_power_at: datetime | None
    pending_command: PendingCommandOutput | None


class ScreenConfigurationOutput(PowerStatusOutput):
    version: str
    items: list[PlaylistItemOutput]


class ScreenStateInput(Schema):
    actual_power_state: str
    command_id: UUID | None = None


class RuntimeStatusInput(Schema):
    agent_version: str = ""
    browser_version: str = ""
    agent_started_at: datetime | None = None
    uptime_seconds: float | None = None
    health_state: str = "unknown"
    health_error: str = ""
    load_1m: float | None = None
    load_5m: float | None = None
    load_15m: float | None = None
    memory_total_bytes: int | None = None
    memory_used_bytes: int | None = None
    memory_available_bytes: int | None = None
    memory_percent: float | None = None
    current_content_id: int | None = None
    last_successful_page_load_at: datetime | None = None
    desired_power_state: str | None = None
    actual_power_state: str | None = None
    display_identity: str = ""
    display_width: int | None = None
    display_height: int | None = None
    display_refresh_rate: float | None = None
    display_orientation: str = ""
    browser_error: str = ""
    display_error: str = ""


class RuntimeStatusOutput(Schema):
    last_check_in: datetime


class EventInput(Schema):
    code: str
    level: str
    message: str
    content_id: int | None = None
    url: str | None = None
    occurred_at: datetime | None = None
    fingerprint: str = ""
    details: dict | None = None


class EventBatchInput(Schema):
    events: list[EventInput]


@router.post(
    "/screens/{token}/status",
    response=RuntimeStatusOutput,
)
def report_runtime_status(
    request,
    token: str,
    payload: RuntimeStatusInput,
):
    screen = get_object_or_404(Screen.objects.all(), public_token=token)
    valid_health_states = set(HealthState.values)
    valid_power_states = set(PowerState.values)
    if payload.health_state not in valid_health_states:
        raise HttpError(400, "invalid health_state")
    if payload.desired_power_state not in valid_power_states | {None, ""}:
        raise HttpError(400, "invalid desired_power_state")
    if payload.actual_power_state not in valid_power_states | {None, ""}:
        raise HttpError(400, "invalid actual_power_state")
    if payload.current_content_id is None:
        current_content = None
    else:
        current_content = get_object_or_404(
            Content.objects.filter(playlist_entries__screen=screen),
            pk=payload.current_content_id,
        )

    for value, name in (
        (payload.uptime_seconds, "uptime_seconds"),
        (payload.load_1m, "load_1m"),
        (payload.load_5m, "load_5m"),
        (payload.load_15m, "load_15m"),
        (payload.memory_percent, "memory_percent"),
        (payload.display_refresh_rate, "display_refresh_rate"),
    ):
        if value is not None and (not math.isfinite(value) or value < 0):
            raise HttpError(400, f"invalid {name}")

    check_in = timezone.now()
    status, _created = ScreenRuntimeStatus.objects.update_or_create(
        screen=screen,
        defaults={
            "agent_version": payload.agent_version[:64],
            "browser_version": payload.browser_version[:256],
            "agent_started_at": utc_datetime(payload.agent_started_at),
            "uptime_seconds": payload.uptime_seconds,
            "last_check_in": check_in,
            "health_state": payload.health_state,
            "health_error": payload.health_error[:2000],
            "load_1m": payload.load_1m,
            "load_5m": payload.load_5m,
            "load_15m": payload.load_15m,
            "memory_total_bytes": payload.memory_total_bytes,
            "memory_used_bytes": payload.memory_used_bytes,
            "memory_available_bytes": payload.memory_available_bytes,
            "memory_percent": payload.memory_percent,
            "current_content": current_content,
            "last_successful_page_load_at": utc_datetime(
                payload.last_successful_page_load_at
            ),
            "desired_power_state": payload.desired_power_state or "",
            "actual_power_state": payload.actual_power_state or "",
            "display_identity": payload.display_identity[:128],
            "display_width": payload.display_width,
            "display_height": payload.display_height,
            "display_refresh_rate": payload.display_refresh_rate,
            "display_orientation": payload.display_orientation[:32],
            "browser_error": payload.browser_error[:2000],
            "display_error": payload.display_error[:2000],
        },
    )
    return {"last_check_in": utc_datetime(status.last_check_in)}


@router.post("/screens/{token}/screenshots")
def upload_screenshot(request, token: str):
    screen = get_object_or_404(Screen.objects.all(), public_token=token)
    try:
        content_id = int(request.POST["content_id"])
        captured_at = datetime.fromisoformat(
            request.POST["captured_at"].replace("Z", "+00:00")
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise HttpError(400, "invalid screenshot metadata") from exc
    captured_at = utc_datetime(captured_at)
    health_state = request.POST.get("health_state", "unknown")
    valid_health_states = set(HealthState.values)
    if health_state not in valid_health_states:
        raise HttpError(400, "invalid health_state")
    content = get_object_or_404(
        Content.objects.filter(playlist_entries__screen=screen),
        pk=content_id,
    )
    image = request.FILES.get("image")
    if image is None or image.size > 2 * 1024 * 1024:
        raise HttpError(
            400, "PNG screenshot is required and must be 2 MiB or smaller"
        )
    if image.content_type not in {None, "image/png"}:
        raise HttpError(400, "screenshot must be PNG")
    if image.read(8) != b"\x89PNG\r\n\x1a\n":
        raise HttpError(400, "screenshot must be PNG")
    image.seek(0)

    screenshot = ScreenContentScreenshot.objects.filter(
        screen=screen, content=content
    ).first()
    if screenshot is not None and captured_at <= screenshot.captured_at:
        return {"stored": False}
    old_name = screenshot.image.name if screenshot is not None else None
    if screenshot is None:
        screenshot = ScreenContentScreenshot(screen=screen, content=content)
    screenshot.captured_at = captured_at
    screenshot.health_state = health_state
    screenshot.error_summary = request.POST.get("error_summary", "")[:2000]
    screenshot.image.save(
        f"{screen.pk}/{content.pk}.png",
        image,
        save=False,
    )
    screenshot.save()
    if old_name and old_name != screenshot.image.name:
        default_storage.delete(old_name)
    return {"stored": True}


@router.post(
    "/screens/{token}/events",
)
def report_events(request, token: str, payload: EventBatchInput):
    screen = get_object_or_404(Screen.objects.all(), public_token=token)
    if not 1 <= len(payload.events) <= 50:
        raise HttpError(400, "events must contain between 1 and 50 entries")
    valid_levels = set(EventLevel.values)
    content_ids = {
        event.content_id
        for event in payload.events
        if event.content_id is not None
    }
    content_map = {
        content.pk: content
        for content in Content.objects.filter(
            playlist_entries__screen=screen,
            pk__in=content_ids,
        )
    }
    if set(content_map) != content_ids:
        raise HttpError(400, "event content is not linked to screen")

    rows = []
    for event in payload.events:
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", event.code):
            raise HttpError(400, "invalid event code")
        if event.level not in valid_levels:
            raise HttpError(400, "invalid event level")
        if not event.message or len(event.message) > 500:
            raise HttpError(
                400, "event message is required and limited to 500 characters"
            )
        details = event.details or {}
        if (
            len(details) > 16
            or any(key not in EVENT_DETAIL_KEYS for key in details)
            or any(len(str(key)) > 64 for key in details)
            or any(
                isinstance(value, (dict, list))
                or (isinstance(value, str) and len(value) > 200)
                for value in details.values()
            )
        ):
            raise HttpError(400, "event details are too large or unsupported")
        sanitized_url = ""
        if event.url:
            parts = urlsplit(event.url)
            netloc = parts.hostname or ""
            try:
                if parts.port:
                    netloc = f"{netloc}:{parts.port}"
            except ValueError:
                netloc = ""
            sanitized_url = urlunsplit(
                (parts.scheme, netloc, parts.path, "", "")
            )[:2048]
        occurred_at = event.occurred_at or timezone.now()
        occurred_at = utc_datetime(occurred_at)
        rows.append(
            Event(
                screen=screen,
                content=content_map.get(event.content_id),
                code=event.code,
                level=event.level,
                message=event.message,
                url=sanitized_url,
                occurred_at=occurred_at,
                fingerprint=event.fingerprint[:128],
                details=details,
            )
        )
    Event.objects.bulk_create(rows)
    return {"accepted": len(rows)}


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
    version, entries = get_screen_configuration(screen)
    response["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return {
        "version": version,
        **power_status(screen),
        "items": [
            {
                "content_id": entry.content_id,
                "url": content_url(screen, entry.content),
                "duration_seconds": entry.duration_seconds,
                "order": entry.order,
                "preload_delay_seconds": effective_preload_delay_seconds(
                    entry.content
                ),
                "preload_timeout_seconds": (
                    effective_preload_timeout_seconds(entry.content)
                ),
                "injected_css": entry.content.injected_css or None,
                "injected_javascript_before": (
                    entry.content.injected_javascript_before or None
                ),
                "injected_javascript_after": (
                    entry.content.injected_javascript_after or None
                ),
            }
            for entry in entries
        ],
    }


@router.post(
    "/screens/{token}/state",
    response=PowerStatusOutput,
)
def report_screen_state(
    request,
    token: str,
    payload: ScreenStateInput,
    response: HttpResponse,
):
    screen = get_object_or_404(Screen.objects.all(), public_token=token)
    valid_states = set(PowerState.values)
    if payload.actual_power_state not in valid_states:
        raise HttpError(400, "invalid actual_power_state")

    pending = screen.pending_command()
    reported_at = timezone.now()
    screen.reported_power_state = payload.actual_power_state
    screen.reported_power_at = reported_at
    screen.save(
        update_fields=[
            "reported_power_state",
            "reported_power_at",
            "updated_at",
        ]
    )
    if pending is not None and payload.command_id == pending.id:
        pending.acknowledged_at = reported_at
        pending.save(update_fields=["acknowledged_at"])
    response["Cache-Control"] = "no-store"
    return power_status(screen)
