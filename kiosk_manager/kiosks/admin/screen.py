from urllib.parse import quote

from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin.utils import display_for_value
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from adminutils import ModelAdmin, object_action, options

from ..forms import ContentAdminForm, ScreenAdminForm
from ..models import (
    HealthState,
    PowerState,
    ScreenContent,
)


def _runtime_status(screen):
    return screen


def _format_duration(seconds):
    if seconds is None:
        return "-"
    try:
        remaining = max(0, int(float(seconds)))
    except TypeError, ValueError, OverflowError:
        return "-"
    days, remaining = divmod(remaining, 86400)
    hours, remaining = divmod(remaining, 3600)
    minutes, seconds = divmod(remaining, 60)
    parts = []
    for value, suffix in (
        (days, "d"),
        (hours, "h"),
        (minutes, "m"),
        (seconds, "s"),
    ):
        if value:
            parts.append(f"{value}{suffix}")
    return " ".join(parts) or "0s"


def _format_load(value):
    return "-" if value is None else f"{value:.2f}"


def _format_bytes(value):
    if value is None:
        return "-"
    try:
        size = float(value)
    except TypeError, ValueError, OverflowError:
        return "-"
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    for unit in units:
        if abs(size) < 1024 or unit == units[-1]:
            precision = 0 if unit == "B" else 1
            return f"{size:.{precision}f} {unit}"
        size /= 1024
    return "-"


def _status_date(value, duration_seconds):
    if value is None:
        return "-"
    date = display_for_value(value, _("unknown"))
    duration = _format_duration(duration_seconds)
    return format_html("{} ({})", date, duration)


def _power_state_icon(state):
    if state == PowerState.ON:
        value = True
    elif state == PowerState.OFF:
        value = False
    else:
        value = None
    return display_for_value(value, _("unknown"), boolean=True)


class ScreenContentInline(admin.TabularInline):
    model = ScreenContent
    extra = 1
    fields = [
        "order",
        "content",
        "duration_seconds",
        "screenshot_image_link",
        "screenshot_captured_at",
        "screenshot_health_state",
        "screenshot_error_summary",
        "screenshot_updated_at",
        "created_at",
        "updated_at",
    ]
    readonly_fields = [
        "screenshot_image_link",
        "screenshot_captured_at",
        "screenshot_health_state",
        "screenshot_error_summary",
        "screenshot_updated_at",
        "created_at",
        "updated_at",
    ]
    ordering = ["order", "pk"]
    verbose_name = _("screen content")
    verbose_name_plural = _("screen content")

    @admin.display(description=_("screenshot"))
    @options(desc=_("Latest diagnostic screenshot"))
    def screenshot_image_link(self, screen_content):
        if not screen_content or not screen_content.screenshot_image:
            return _("none")
        return format_html(
            '<a href="{}" target="_blank">View screenshot</a>',
            screen_content.screenshot_image.url,
        )


class ContentAdmin(ModelAdmin):
    form = ContentAdminForm
    fieldsets = [
        (
            _("Content").upper(),
            {
                "fields": [
                    "id",
                    "label",
                    "url",
                    "html_upload",
                    "media",
                    "preload_delay_seconds",
                    "preload_timeout_seconds",
                    "injected_css",
                    "injected_javascript_before",
                    "injected_javascript_after",
                ],
            },
        ),
        (
            _("Timestamps").upper(),
            {
                "fields": [
                    "created_at",
                    "updated_at",
                ],
            },
        ),
    ]
    list_display = ["label", "preload_delay_seconds", "updated_at"]
    list_filter = ["created_at", "updated_at"]
    search_fields = ["label", "url", "html", "media"]
    readonly_fields = ["id", "created_at", "updated_at"]
    ordering = ["-updated_at", "pk"]
    date_hierarchy = "created_at"


class ScreenAdmin(ModelAdmin):
    form = ScreenAdminForm
    view_on_site = True
    fieldsets = [
        (
            _("Screen").upper(),
            {
                "fields": [
                    "id",
                    "name",
                    "public_token",
                    "enabled",
                ],
            },
        ),
        (
            _("Status").upper(),
            {
                "fields": [
                    "agent_browser_version_display",
                    "agent_uptime_display",
                    "last_check_in_display",
                    "health_display",
                    "pending_agent_command_display",
                    "load_display",
                    "memory_display",
                    "display_info_display",
                    "desired_power_state_display",
                    "reported_power_state_display",
                ],
            },
        ),
        (
            _("Power schedule").upper(),
            {
                "fields": [
                    "on_schedule",
                    "off_schedule",
                ],
            },
        ),
        (
            _("Agent installation").upper(),
            {
                "classes": ["collapse"],
                "fields": [
                    "agent_install_url",
                    "agent_install_command",
                ],
            },
        ),
        (
            _("Timestamps").upper(),
            {
                "classes": ["collapse"],
                "fields": [
                    "created_at",
                    "updated_at",
                ],
            },
        ),
    ]
    list_display = ["name", "enabled", "updated_at"]
    list_filter = ["enabled", "created_at", "updated_at"]
    search_fields = [
        "name",
        "public_token",
        "playlist_entries__content__url",
        "playlist_entries__content__html",
        "playlist_entries__content__media",
    ]
    readonly_fields = [
        "id",
        "public_token",
        "agent_install_url",
        "agent_install_command",
        "desired_power_state_display",
        "reported_power_state_display",
        "pending_agent_command_display",
        "agent_browser_version_display",
        "agent_uptime_display",
        "last_check_in_display",
        "health_display",
        "load_display",
        "memory_display",
        "display_info_display",
        "created_at",
        "updated_at",
    ]
    ordering = ["name", "pk"]
    date_hierarchy = "created_at"
    inlines = [ScreenContentInline]
    change_actions = [
        "screen_on_action",
        "screen_off_action",
        "follow_schedule_action",
        "restart_agent_action",
        "upgrade_agent_action",
        "clear_pending_commands_action",
        "rotate_public_token_action",
    ]

    def _agent_install_url(self, screen):
        if not screen.enabled:
            return ""
        origin = settings.SITE_BASE_URL
        if not origin:
            hosts = [host for host in settings.ALLOWED_HOSTS if host != "*"]
            origin = f"https://{hosts[0]}" if hosts else "https://localhost"
        return (
            f"{origin}{reverse('kiosks:agent-install')}?screen="
            f"{quote(screen.public_token, safe='')}"
        )

    @admin.display(description=_("agent install URL"))
    @options(desc=_("HTTPS command URL for this screen's agent"))
    def agent_install_url(self, screen):
        url = self._agent_install_url(screen)
        return (
            format_html('<a href="{0}">{0}</a>', url)
            if url
            else _("Enable screen to generate an installer.")
        )

    @admin.display(description=_("agent install command"))
    @options(desc=_("Run on the target Debian host"))
    def agent_install_command(self, screen):
        url = self._agent_install_url(screen)
        if not url:
            return _("Enable screen to generate an installer.")
        return format_html("<code>curl -fsSL {0} | bash</code>", url)

    @admin.display(description=_("desired power state"))
    @options(desc=_("Power state currently desired by schedule or override"))
    def desired_power_state_display(self, screen):
        state = screen.desired_power_state()
        icon = _power_state_icon(state)
        if screen.power_override:
            return format_html("{} ({})", icon, _("overridden"))
        next_change = screen.next_scheduled_power_change()
        if next_change is None:
            return icon
        next_at, _next_state = next_change
        next_change_display = display_for_value(next_at, _("unknown"))
        return format_html(
            "{} ({})",
            icon,
            _("next change: %(next_change)s")
            % {"next_change": next_change_display},
        )

    @admin.display(description=_("reported power state"))
    @options(desc=_("Last power state reported by kiosk agent"))
    def reported_power_state_display(self, screen):
        icon = _power_state_icon(screen.status_power_state)
        if screen.status_power_at is None:
            return icon
        reported_at = display_for_value(screen.status_power_at, _("unknown"))
        return format_html(
            "{} ({})",
            icon,
            _("last changed at: %(reported_at)s")
            % {"reported_at": reported_at},
        )

    @admin.display(description=_("Pending commands"))
    @options(desc=_("Unacknowledged command waiting for agent"))
    def pending_agent_command_display(self, screen):
        command = screen.pending_command()
        if command is None:
            return "-"
        created_at = display_for_value(command.created_at, _("unknown"))
        created_by = (
            str(command.created_by)
            if command.created_by is not None
            else _("system")
        )
        return format_html(
            "<code>{}</code> ({}, {})",
            command.command,
            _("created at: %(created_at)s") % {"created_at": created_at},
            _("by: %(created_by)s") % {"created_by": created_by},
        )

    @admin.display(description=_("Agent Version"))
    @options(desc=_("Versions reported by kiosk agent"))
    def agent_browser_version_display(self, screen):
        status = _runtime_status(screen)
        if status is None:
            return "-"
        return format_html(
            "{} ({})",
            status.status_agent_version or "-",
            status.status_browser_version or "-",
        )

    @admin.display(description=_("Agent Uptime"))
    @options(desc=_("Agent start time and reported uptime"))
    def agent_uptime_display(self, screen):
        status = _runtime_status(screen)
        if status is None:
            return "-"
        uptime = status.status_uptime_seconds
        if uptime is None and status.status_agent_started_at is not None:
            uptime = (
                timezone.now() - status.status_agent_started_at
            ).total_seconds()
        return _status_date(status.status_agent_started_at, uptime)

    @admin.display(description=_("Last Check-In"))
    @options(desc=_("Last status report and elapsed time"))
    def last_check_in_display(self, screen):
        status = _runtime_status(screen)
        if status is None or status.status_last_check_in is None:
            return "-"
        age = (timezone.now() - status.status_last_check_in).total_seconds()
        return _status_date(status.status_last_check_in, age)

    @admin.display(description=_("Health"))
    @options(desc=_("Health state and browser/display errors"))
    def health_display(self, screen):
        status = _runtime_status(screen)
        if status is None:
            return "-"
        health_state = status.status_health_state
        health_issue = (
            health_state in {HealthState.DEGRADED, HealthState.ERROR}
            or bool(status.status_health_error)
            or bool(status.status_browser_error)
            or bool(status.status_display_error)
        )
        lines = [
            display_for_value(not health_issue, _("unknown"), boolean=True),
        ]
        if status.status_health_error:
            lines.append(
                format_html("{}: {}", _("Health"), status.status_health_error)
            )
        elif health_state in {HealthState.DEGRADED, HealthState.ERROR}:
            lines.append(
                format_html(
                    "{}: {}",
                    _("Health"),
                    (
                        status.get_status_health_state_display()
                        or health_state
                    ).title(),
                )
            )
        for label, error in (
            (_("Browser"), status.status_browser_error),
            (_("Display"), status.status_display_error),
        ):
            if error:
                lines.append(format_html("{}: {}", label, error))
        return format_html_join(
            mark_safe("<br>"),
            "{}",
            ((line,) for line in lines),
        )

    @admin.display(description=_("Load"))
    @options(desc=_("One-, five-, and fifteen-minute load"))
    def load_display(self, screen):
        status = _runtime_status(screen)
        if status is None:
            return "-"
        return format_html(
            "1m: {} · 5m: {} · 15m: {}",
            _format_load(status.status_load_1m),
            _format_load(status.status_load_5m),
            _format_load(status.status_load_15m),
        )

    @admin.display(description=_("Memory"))
    @options(desc=_("Used and total memory with percentage"))
    def memory_display(self, screen):
        status = _runtime_status(screen)
        if status is None:
            return "-"
        percent = (
            "-"
            if status.status_memory_percent is None
            else f"{status.status_memory_percent:.1f}%"
        )
        return format_html(
            "{} / {} used ({})",
            _format_bytes(status.status_memory_used_bytes),
            _format_bytes(status.status_memory_total_bytes),
            percent,
        )

    @admin.display(description=_("Display"))
    @options(desc=_("Display name, resolution, and refresh rate"))
    def display_info_display(self, screen):
        status = _runtime_status(screen)
        if status is None:
            return "-"
        dimensions = (
            f"{status.status_display_width} x {status.status_display_height}"
            if status.status_display_width is not None
            and status.status_display_height is not None
            else "-"
        )
        refresh = (
            "-"
            if status.status_display_refresh_rate is None
            else f"{status.status_display_refresh_rate:.1f} Hz"
        )
        return format_html(
            "{} · {} @ {}",
            status.status_display_identity or "-",
            dimensions,
            refresh,
        )

    @object_action
    @options(
        label=_("Screen on"),
        desc=_("Temporarily override power schedule and turn screen on"),
    )
    def screen_on_action(self, request, screen):
        screen.power_override = PowerState.ON
        screen.save(update_fields=["power_override", "updated_at"])
        messages.success(request, _("Screen on override enabled."))

    @object_action
    @options(
        label=_("Screen off"),
        desc=_("Temporarily override power schedule and turn screen off"),
    )
    def screen_off_action(self, request, screen):
        screen.power_override = PowerState.OFF
        screen.save(update_fields=["power_override", "updated_at"])
        messages.success(request, _("Screen off override enabled."))

    @object_action
    @options(
        label=_("Follow schedule"),
        desc=_("Clear temporary power override"),
    )
    def follow_schedule_action(self, request, screen):
        screen.power_override = ""
        screen.save(update_fields=["power_override", "updated_at"])
        messages.success(request, _("Screen now follows schedule."))

    @object_action
    @options(
        label=_("Restart agent"),
        desc=_("Queue one restart command for kiosk agent"),
    )
    def restart_agent_action(self, request, screen):
        command = screen.request_agent_restart(created_by=request.user)
        messages.success(
            request,
            _("Agent restart command queued: %(id)s") % {"id": command.id},
        )

    @object_action
    @options(
        label=_("Upgrade agent"),
        desc=_("Queue an agent upgrade and restart"),
    )
    def upgrade_agent_action(self, request, screen):
        command = screen.request_agent_upgrade(created_by=request.user)
        messages.success(
            request,
            _("Agent upgrade command queued: %(id)s") % {"id": command.id},
        )

    @object_action
    @options(
        label=_("Clear pending commands"),
        desc=_("Acknowledge all unacknowledged commands for this screen"),
    )
    def clear_pending_commands_action(self, request, screen):
        count = screen.clear_pending_commands()
        messages.success(
            request,
            _("Cleared %(count)d pending command(s).") % {"count": count},
        )

    @object_action
    @options(
        label=_("Rotate public token"),
        desc=_("Invalidate existing display URLs and issue a new token"),
    )
    def rotate_public_token_action(self, request, screen):
        screen.rotate_public_token()
        display_url = (
            f"{settings.SITE_BASE_PATH}/screens/{screen.public_token}/"
        )
        messages.success(
            request,
            _("Public token rotated. New display URL: %(url)s")
            % {"url": display_url},
        )
