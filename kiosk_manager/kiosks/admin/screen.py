from urllib.parse import quote

from django.conf import settings
from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from adminutils import ModelAdmin, object_action, options

from ..models import PowerState, ScreenContent


class ScreenContentInline(admin.TabularInline):
    model = ScreenContent
    extra = 1
    fields = [
        "order",
        "content",
        "duration_seconds",
        "created_at",
        "updated_at",
    ]
    readonly_fields = ["created_at", "updated_at"]
    ordering = ["order", "pk"]
    verbose_name = _("screen content")
    verbose_name_plural = _("screen content")


class ContentAdmin(ModelAdmin):
    fieldsets = [
        (
            _("Content").upper(),
            {
                "fields": [
                    "id",
                    "url",
                    "html_file",
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
    list_display = ["source_display", "preload_delay_seconds", "updated_at"]
    list_filter = ["created_at", "updated_at"]
    search_fields = ["url", "html_file"]
    readonly_fields = ["id", "created_at", "updated_at"]
    ordering = ["-updated_at", "pk"]
    date_hierarchy = "created_at"

    @admin.display(description=_("source"))
    @options(desc=_("URL or uploaded HTML file"))
    def source_display(self, content):
        return str(content)


class ScreenAdmin(ModelAdmin):
    fieldsets = [
        (
            _("Screen").upper(),
            {
                "fields": [
                    "id",
                    "name",
                    "enabled",
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
            _("Remote state").upper(),
            {
                "fields": [
                    "power_override",
                    "desired_power_state_display",
                    "reported_power_state",
                    "reported_power_at",
                    "pending_agent_command_display",
                ],
            },
        ),
        (
            _("Public access").upper(),
            {
                "fields": [
                    "public_token",
                    "display_url",
                ],
            },
        ),
        (
            _("Agent installation").upper(),
            {
                "fields": [
                    "agent_install_url",
                    "agent_install_command",
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
    list_display = ["name", "enabled", "display_url", "updated_at"]
    list_filter = ["enabled", "created_at", "updated_at"]
    search_fields = [
        "name",
        "public_token",
        "playlist_entries__content__url",
        "playlist_entries__content__html_file",
    ]
    readonly_fields = [
        "id",
        "public_token",
        "display_url",
        "agent_install_url",
        "agent_install_command",
        "power_override",
        "desired_power_state_display",
        "reported_power_state",
        "reported_power_at",
        "pending_agent_command_display",
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
        "rotate_public_token_action",
    ]

    @admin.display(description=_("display URL"))
    @options(desc=_("Public URL for this screen"))
    def display_url(self, screen):
        display_url = (
            f"{settings.SITE_BASE_PATH}/screens/{screen.public_token}/"
        )
        return format_html('<a href="{0}">{0}</a>', display_url)

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
        return screen.desired_power_state() or _("unknown")

    @admin.display(description=_("pending agent command"))
    @options(desc=_("Unacknowledged command waiting for agent"))
    def pending_agent_command_display(self, screen):
        command = screen.pending_command()
        return command.command if command is not None else _("none")

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
        command = screen.request_agent_restart()
        messages.success(
            request,
            _("Agent restart command queued: %(id)s") % {"id": command.id},
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
