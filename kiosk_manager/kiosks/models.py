import secrets
import uuid
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.validators import (
    FileExtensionValidator,
    MaxLengthValidator,
    MinValueValidator,
    RegexValidator,
)
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

import magic
from recurrence.fields import RecurrenceField

DEFAULT_PRELOAD_DELAY_SECONDS = Decimal("0")
DEFAULT_PRELOAD_TIMEOUT_SECONDS = 30


class PowerOverride(models.TextChoices):
    ON = "on", _("on")
    OFF = "off", _("off")


class PowerState(models.TextChoices):
    ON = "on", _("on")
    OFF = "off", _("off")
    UNKNOWN = "unknown", _("unknown")


class ScreenCommandChoice(models.TextChoices):
    RESTART_AGENT = "restart_agent", _("restart agent")


COMMAND_RESTART_AGENT = ScreenCommandChoice.RESTART_AGENT


class HealthState(models.TextChoices):
    UNKNOWN = "unknown", _("unknown")
    HEALTHY = "healthy", _("healthy")
    DEGRADED = "degraded", _("degraded")
    ERROR = "error", _("error")


class EventLevel(models.TextChoices):
    DEBUG = "DEBUG", _("debug")
    INFO = "INFO", _("info")
    WARNING = "WARNING", _("warning")
    ERROR = "ERROR", _("error")
    CRITICAL = "CRITICAL", _("critical")


class MediaKind(models.TextChoices):
    IMAGE = "image", _("image")
    VIDEO = "video", _("video")


MAX_HTML_LENGTH = 1024 * 1024
MEDIA_FORMATS = {
    ".jpg": (MediaKind.IMAGE, "image/jpeg"),
    ".jpeg": (MediaKind.IMAGE, "image/jpeg"),
    ".png": (MediaKind.IMAGE, "image/png"),
    ".gif": (MediaKind.IMAGE, "image/gif"),
    ".webp": (MediaKind.IMAGE, "image/webp"),
    ".avif": (MediaKind.IMAGE, "image/avif"),
    ".svg": (MediaKind.IMAGE, "image/svg+xml"),
    ".mp4": (MediaKind.VIDEO, "video/mp4"),
    ".webm": (MediaKind.VIDEO, "video/webm"),
}
MEDIA_MIME_ALIASES = {
    "image/svg+xml": {"image/svg+xml", "application/xml", "text/xml"},
}


def media_format_for_name(name: str) -> tuple[MediaKind, str]:
    extension = Path(name).suffix.lower()
    try:
        return MEDIA_FORMATS[extension]
    except KeyError as exc:
        raise ValidationError(
            {"media": _("Unsupported media file format.")}
        ) from exc


def validate_media_upload(uploaded_file):
    _kind, expected_mime = media_format_for_name(uploaded_file.name or "")
    position = uploaded_file.tell()
    try:
        uploaded_file.seek(0)
        detected_mime = magic.from_buffer(uploaded_file.read(8192), mime=True)
    except (OSError, TypeError, ValueError, magic.MagicException) as exc:
        raise ValidationError(
            {"media": _("Could not inspect media file.")}
        ) from exc
    finally:
        uploaded_file.seek(position)
    accepted_mimes = MEDIA_MIME_ALIASES.get(expected_mime, {expected_mime})
    if detected_mime not in accepted_mimes:
        raise ValidationError(
            {
                "media": _(
                    "Media content does not match its file extension "
                    "(%(mime)s detected)."
                )
                % {"mime": detected_mime}
            }
        )
    return _kind, expected_mime


HEALTH_UNKNOWN = HealthState.UNKNOWN
HEALTH_HEALTHY = HealthState.HEALTHY
HEALTH_DEGRADED = HealthState.DEGRADED
HEALTH_ERROR = HealthState.ERROR
EVENT_CODE_VALIDATOR = RegexValidator(
    regex=r"^[a-z][a-z0-9_]{1,63}$",
    message=_("Use lowercase letters, numbers, and underscores."),
)


def _schedule_occurrence(schedule, current, direction):
    dtstart = None
    if schedule.dtstart is None:
        dtstart = current.replace(year=1970, month=1, day=1)
    try:
        occurrence = getattr(schedule, direction)(
            current, inc=True, dtstart=dtstart
        )
    except TypeError as exc:
        try:
            naive_current = timezone.make_naive(
                current, timezone.get_current_timezone()
            )
            naive_dtstart = (
                timezone.make_naive(dtstart, timezone.get_current_timezone())
                if dtstart is not None
                else None
            )
            occurrence = getattr(schedule, direction)(
                naive_current,
                inc=True,
                dtstart=naive_dtstart,
            )
        except TypeError as fallback_exc:
            raise exc from fallback_exc
    if occurrence is not None and timezone.is_naive(occurrence):
        occurrence = timezone.make_aware(
            occurrence, timezone.get_current_timezone()
        )
    return occurrence


def _schedule_before(schedule, current):
    return _schedule_occurrence(schedule, current, "before")


def _schedule_after(schedule, current):
    return _schedule_occurrence(schedule, current, "after")


def generate_public_token():
    return secrets.token_urlsafe(32)


class Screen(models.Model):
    name = models.CharField(_("name"), max_length=200)
    public_token = models.CharField(
        _("public token"),
        max_length=64,
        unique=True,
        default=generate_public_token,
        editable=False,
    )
    enabled = models.BooleanField(
        _("enabled"),
        default=True,
    )
    contents = models.ManyToManyField(
        "Content",
        through="ScreenContent",
        related_name="screens",
        verbose_name=_("contents"),
        blank=True,
    )
    on_schedule = RecurrenceField(
        include_dtstart=False,
        blank=True,
        default="",
        verbose_name=_("power-on schedule"),
        help_text=_(
            "Optional recurring times when screen should receive HDMI-CEC "
            "on command. Times use the server timezone."
        ),
    )
    off_schedule = RecurrenceField(
        include_dtstart=False,
        blank=True,
        default="",
        verbose_name=_("power-off schedule"),
        help_text=_(
            "Optional recurring times when screen should receive HDMI-CEC "
            "standby command. Times use the server timezone."
        ),
    )
    power_override = models.CharField(
        _("temporary power override"),
        max_length=16,
        choices=PowerOverride.choices,
        blank=True,
        default="",
        help_text=_(
            "Temporary on/off override. Clear to follow configured schedule."
        ),
    )
    reported_power_state = models.CharField(
        _("reported power state"),
        max_length=16,
        choices=PowerState.choices,
        default=PowerState.UNKNOWN,
        help_text=_("Last power state reported by kiosk agent."),
    )
    reported_power_at = models.DateTimeField(
        _("reported power at"),
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = _("screen")
        verbose_name_plural = _("screens")

    def __str__(self):
        return str(self.name)

    def get_absolute_url(self):
        return reverse(
            "kiosks:screen-display",
            kwargs={"token": self.public_token},
        )

    def rotate_public_token(self):
        self.public_token = generate_public_token()
        self.save(update_fields=["public_token", "updated_at"])

    def scheduled_power_state(self, at=None):
        current = at or timezone.now()
        if timezone.is_naive(current):
            current = timezone.make_aware(
                current, timezone.get_current_timezone()
            )
        events = []
        for state, schedule in (
            (PowerState.ON, self.on_schedule),
            (PowerState.OFF, self.off_schedule),
        ):
            if schedule:
                occurrence = _schedule_before(schedule, current)
                if occurrence is not None:
                    events.append((occurrence, state))
        if not events:
            return None
        return max(events, key=lambda event: event[0])[1]

    def next_scheduled_power_change(self, at=None):
        current = at or timezone.now()
        if timezone.is_naive(current):
            current = timezone.make_aware(
                current, timezone.get_current_timezone()
            )
        current_state = self.scheduled_power_state(current)
        if current_state == PowerState.ON:
            next_state = PowerState.OFF
            schedule = self.off_schedule
        elif current_state == PowerState.OFF:
            next_state = PowerState.ON
            schedule = self.on_schedule
        else:
            return None
        if not schedule:
            return None
        occurrence = _schedule_after(schedule, current)
        if occurrence is None:
            return None
        return occurrence, next_state

    def desired_power_state(self, at=None):
        if self.power_override:
            return self.power_override
        scheduled = self.scheduled_power_state(at)
        if scheduled is not None:
            return scheduled
        if not self.on_schedule and not self.off_schedule:
            return PowerState.ON
        return None

    def pending_command(self, command=None):
        commands = self.commands.filter(acknowledged_at__isnull=True)
        if command is not None:
            commands = commands.filter(command=command)
        return commands.order_by("-created_at").first()

    def request_agent_restart(self, created_by=None):
        with transaction.atomic():
            screen = type(self).objects.select_for_update().get(pk=self.pk)
            pending = screen.pending_command(COMMAND_RESTART_AGENT)
            if pending is not None:
                return pending
            return ScreenCommand.objects.create(
                screen=screen,
                command=COMMAND_RESTART_AGENT,
                created_by=created_by,
            )

    def clear_pending_commands(self, acknowledged_at=None):
        return self.commands.filter(acknowledged_at__isnull=True).update(
            acknowledged_at=acknowledged_at or timezone.now()
        )


class ScreenCommand(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name=_("id"),
    )
    screen = models.ForeignKey(
        Screen,
        verbose_name=_("screen"),
        related_name="commands",
        on_delete=models.CASCADE,
    )
    command = models.CharField(
        _("command"),
        max_length=32,
        choices=ScreenCommandChoice.choices,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("created by"),
        related_name="kiosk_screen_commands",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    acknowledged_at = models.DateTimeField(
        _("acknowledged at"),
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ["-created_at", "id"]
        verbose_name = _("screen command")
        verbose_name_plural = _("screen commands")
        constraints = [
            models.UniqueConstraint(
                fields=["screen", "command"],
                condition=models.Q(acknowledged_at__isnull=True),
                name="kiosks_pending_command_unique",
            ),
        ]

    def __str__(self):
        return f"{self.screen} · {self.command} · {self.id}"


class Content(models.Model):
    label = models.CharField(
        _("label"),
        max_length=200,
        default="",
    )
    url = models.URLField(
        _("URL"),
        max_length=2048,
        blank=True,
        default="",
    )
    html = models.TextField(
        _("HTML"),
        blank=True,
        default="",
        max_length=MAX_HTML_LENGTH,
        validators=[MaxLengthValidator(MAX_HTML_LENGTH)],
        help_text=_("Full self-contained HTML document."),
    )
    media = models.FileField(
        _("media file"),
        upload_to="contents/",
        blank=True,
        default="",
        validators=[
            FileExtensionValidator(
                [Path(extension).name[1:] for extension in MEDIA_FORMATS]
            )
        ],
        help_text=_("Upload a Chrome-compatible image or video."),
    )
    preload_delay_seconds = models.DecimalField(
        _("preload delay (seconds)"),
        max_digits=8,
        decimal_places=2,
        default=DEFAULT_PRELOAD_DELAY_SECONDS,
        validators=[MinValueValidator(0)],
        help_text=_(
            "Start loading this many seconds before display. Zero starts "
            "loading at the display transition."
        ),
    )
    preload_timeout_seconds = models.PositiveIntegerField(
        _("preload timeout (seconds)"),
        default=DEFAULT_PRELOAD_TIMEOUT_SECONDS,
        validators=[MinValueValidator(1)],
        help_text=_(
            "Maximum seconds from navigation request before displaying "
            "content, regardless of loading state."
        ),
    )
    injected_css = models.TextField(
        _("injected CSS"),
        blank=True,
        default="",
        max_length=65536,
        validators=[MaxLengthValidator(65536)],
        help_text=_("Optional CSS applied on every document load."),
    )
    injected_javascript_before = models.TextField(
        _("JavaScript before page scripts"),
        blank=True,
        default="",
        max_length=65536,
        validators=[MaxLengthValidator(65536)],
        help_text=_("Optional JavaScript executed before page scripts."),
    )
    injected_javascript_after = models.TextField(
        _("JavaScript after document load"),
        blank=True,
        default="",
        max_length=65536,
        validators=[MaxLengthValidator(65536)],
        help_text=_("Optional JavaScript executed after document load."),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ["-updated_at", "pk"]
        verbose_name = _("content")
        verbose_name_plural = _("content")
        constraints = [
            models.CheckConstraint(
                condition=(
                    (
                        ~models.Q(url="")
                        & models.Q(html="")
                        & models.Q(media="")
                    )
                    | (
                        models.Q(url="")
                        & ~models.Q(html="")
                        & models.Q(media="")
                    )
                    | (
                        models.Q(url="")
                        & models.Q(html="")
                        & ~models.Q(media="")
                    )
                ),
                name="kiosks_content_single_source",
            ),
        ]

    def __str__(self):
        return self.label or self.url or self.media.name or _("HTML content")

    def save(self, *args, **kwargs):
        old_media_name = ""
        if self.pk:
            old_media_name = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("media", flat=True)
                .first()
                or ""
            )
        super().save(*args, **kwargs)
        new_media_name = self.media.name or ""
        if old_media_name and old_media_name != new_media_name:
            default_storage.delete(old_media_name)

    def delete(self, *args, **kwargs):
        media_name = self.media.name or ""
        result = super().delete(*args, **kwargs)
        if media_name:
            default_storage.delete(media_name)
        return result

    def clean(self):
        super().clean()
        has_url = bool(self.url)
        has_html = bool(self.html)
        has_media = bool(self.media)
        if sum((has_url, has_html, has_media)) != 1:
            message = _(
                "Provide exactly one URL, HTML document, or media file."
            )
            raise ValidationError(message)
        if has_media:
            media_format_for_name(self.media.name)


class ScreenRuntimeStatus(models.Model):
    screen = models.OneToOneField(
        Screen,
        verbose_name=_("screen"),
        related_name="runtime_status",
        on_delete=models.CASCADE,
    )
    agent_version = models.CharField(
        _("agent version"), max_length=64, blank=True
    )
    browser_version = models.CharField(
        _("browser version"), max_length=256, blank=True
    )
    agent_started_at = models.DateTimeField(
        _("agent started at"), blank=True, null=True
    )
    uptime_seconds = models.FloatField(
        _("uptime (seconds)"), blank=True, null=True
    )
    last_check_in = models.DateTimeField(
        _("last check-in"), blank=True, null=True
    )
    health_state = models.CharField(
        _("health state"),
        max_length=16,
        choices=HealthState.choices,
        default=HEALTH_UNKNOWN,
    )
    health_error = models.TextField(_("health error"), blank=True)
    load_1m = models.FloatField(_("one-minute load"), blank=True, null=True)
    load_5m = models.FloatField(_("five-minute load"), blank=True, null=True)
    load_15m = models.FloatField(
        _("fifteen-minute load"), blank=True, null=True
    )
    memory_total_bytes = models.BigIntegerField(
        _("memory total (bytes)"), blank=True, null=True
    )
    memory_used_bytes = models.BigIntegerField(
        _("memory used (bytes)"), blank=True, null=True
    )
    memory_available_bytes = models.BigIntegerField(
        _("memory available (bytes)"), blank=True, null=True
    )
    memory_percent = models.FloatField(
        _("memory used (percent)"), blank=True, null=True
    )
    current_content = models.ForeignKey(
        "Content",
        verbose_name=_("current content"),
        related_name="runtime_statuses",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )
    last_successful_page_load_at = models.DateTimeField(
        _("last successful page load at"), blank=True, null=True
    )
    desired_power_state = models.CharField(
        _("desired power state"),
        max_length=16,
        choices=PowerState.choices,
        blank=True,
        default="",
    )
    actual_power_state = models.CharField(
        _("actual power state"),
        max_length=16,
        choices=PowerState.choices,
        blank=True,
        default="",
    )
    display_identity = models.CharField(
        _("display identity"), max_length=128, blank=True
    )
    display_width = models.PositiveIntegerField(
        _("display width"), blank=True, null=True
    )
    display_height = models.PositiveIntegerField(
        _("display height"), blank=True, null=True
    )
    display_refresh_rate = models.FloatField(
        _("display refresh rate"), blank=True, null=True
    )
    display_orientation = models.CharField(
        _("display orientation"), max_length=32, blank=True
    )
    browser_error = models.TextField(_("browser error"), blank=True)
    display_error = models.TextField(_("display error"), blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ["-last_check_in", "screen_id"]
        verbose_name = _("screen runtime status")
        verbose_name_plural = _("screen runtime statuses")
        indexes = [
            models.Index(
                fields=["health_state", "last_check_in"],
                name="kiosks_status_health_check",
            ),
        ]

    def __str__(self):
        return f"{self.screen} · {self.health_state}"


class ScreenContentScreenshot(models.Model):
    screen = models.ForeignKey(
        Screen,
        verbose_name=_("screen"),
        related_name="content_screenshots",
        on_delete=models.CASCADE,
    )
    content = models.ForeignKey(
        "Content",
        verbose_name=_("content"),
        related_name="screenshots",
        on_delete=models.CASCADE,
    )
    image = models.FileField(
        _("screenshot"),
        upload_to="screenshots/",
    )
    captured_at = models.DateTimeField(_("captured at"))
    health_state = models.CharField(
        _("health state"),
        max_length=16,
        choices=HealthState.choices,
        default=HEALTH_UNKNOWN,
    )
    error_summary = models.TextField(_("error summary"), blank=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ["-captured_at", "screen_id", "content_id"]
        verbose_name = _("screen content screenshot")
        verbose_name_plural = _("screen content screenshots")
        constraints = [
            models.UniqueConstraint(
                fields=["screen", "content"],
                name="kiosks_screenshot_screen_content_unique",
            ),
        ]

    def __str__(self):
        return f"{self.screen} · {self.content} · {self.captured_at}"


class Event(models.Model):
    screen = models.ForeignKey(
        Screen,
        verbose_name=_("screen"),
        related_name="events",
        on_delete=models.CASCADE,
    )
    content = models.ForeignKey(
        Content,
        verbose_name=_("content"),
        related_name="events",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )
    code = models.CharField(
        _("event code"),
        max_length=64,
        validators=[EVENT_CODE_VALIDATOR],
    )
    level = models.CharField(
        _("level"), max_length=16, choices=EventLevel.choices
    )
    message = models.CharField(_("message"), max_length=500)
    url = models.URLField(_("URL"), max_length=2048, blank=True)
    occurred_at = models.DateTimeField(_("occurred at"))
    received_at = models.DateTimeField(_("received at"), auto_now_add=True)
    fingerprint = models.CharField(
        _("fingerprint"), max_length=128, blank=True
    )
    details = models.JSONField(_("details"), default=dict, blank=True)

    class Meta:
        ordering = ["-received_at", "-pk"]
        verbose_name = _("event")
        verbose_name_plural = _("events")
        indexes = [
            models.Index(
                fields=["screen", "-received_at"],
                name="kiosks_event_screen_received",
            ),
            models.Index(
                fields=["screen", "code", "-received_at"],
                name="kiosks_event_code_received",
            ),
            models.Index(fields=["received_at"], name="kiosks_event_received"),
        ]

    def __str__(self):
        return f"{self.screen} · {self.level} · {self.code}"


class ScreenContent(models.Model):
    screen = models.ForeignKey(
        Screen,
        verbose_name=_("screen"),
        related_name="playlist_entries",
        on_delete=models.CASCADE,
    )
    content = models.ForeignKey(
        Content,
        verbose_name=_("content"),
        related_name="playlist_entries",
        on_delete=models.CASCADE,
    )
    duration_seconds = models.PositiveIntegerField(
        _("time on page (seconds)"),
        validators=[MinValueValidator(1)],
        default=30,
    )
    order = models.PositiveIntegerField(
        _("order"),
        validators=[MinValueValidator(1)],
        default=1,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ["order", "pk"]
        verbose_name = _("screen content")
        verbose_name_plural = _("screen content")
        constraints = [
            models.UniqueConstraint(
                fields=["screen", "order"],
                name="kiosks_screen_content_order_unique",
            ),
        ]

    def __str__(self):
        return f"{self.screen} · {self.order} · {self.content}"
