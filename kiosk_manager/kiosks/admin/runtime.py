from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from admin_auto_filters.filters import AutocompleteFilterFactory
from adminutils import ModelAdmin

from ..models import Event, EventLevel

_EVENT_LEVEL_COLORS = {
    EventLevel.DEBUG: "#6b7280",
    EventLevel.INFO: "#2563eb",
    EventLevel.WARNING: "#d97706",
    EventLevel.ERROR: "#dc2626",
    EventLevel.CRITICAL: "#991b1b",
}


class EventAdmin(ModelAdmin):
    list_display = [
        "screen",
        "level_display",
        "code",
        "content",
        "message",
        "occurred_at",
        "received_at",
    ]
    list_filter = [
        AutocompleteFilterFactory(_("screen"), "screen"),
        AutocompleteFilterFactory(_("content"), "content"),
        "level",
        "code",
        "received_at",
    ]
    search_fields = [
        "screen__name",
        "content__url",
        "message",
        "fingerprint",
    ]
    readonly_fields = [field.name for field in Event._meta.fields]
    ordering = ["-received_at", "-pk"]
    date_hierarchy = "received_at"

    @admin.display(description=_("level"), ordering="level")
    def level_display(self, event):
        color = _EVENT_LEVEL_COLORS.get(
            event.level, _EVENT_LEVEL_COLORS[EventLevel.INFO]
        )
        return format_html(
            '<span style="color: {}; font-weight: 600;">{}</span>',
            color,
            event.get_level_display().title(),
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
