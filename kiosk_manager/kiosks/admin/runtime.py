from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from adminutils import ModelAdmin, options

from ..models import Event, ScreenRuntimeStatus


class ScreenRuntimeStatusAdmin(ModelAdmin):
    list_display = [
        "screen",
        "health_state",
        "last_check_in",
        "current_content",
        "display_identity",
    ]
    list_filter = ["health_state", "last_check_in"]
    search_fields = ["screen__name", "screen__public_token", "health_error"]
    readonly_fields = [
        field.name
        for field in ScreenRuntimeStatus._meta.fields
        if field.name != "id"
    ]
    ordering = ["-last_check_in", "screen_id"]
    date_hierarchy = "last_check_in"

    def has_add_permission(self, request):
        return False


class EventAdmin(ModelAdmin):
    list_display = [
        "screen",
        "level",
        "code",
        "content",
        "message",
        "occurred_at",
        "received_at",
    ]
    list_filter = ["level", "code", "screen", "received_at"]
    search_fields = [
        "screen__name",
        "content__url",
        "message",
        "fingerprint",
    ]
    readonly_fields = [field.name for field in Event._meta.fields]
    ordering = ["-received_at", "-pk"]
    date_hierarchy = "received_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ScreenContentScreenshotAdmin(ModelAdmin):
    list_display = [
        "screen",
        "content",
        "captured_at",
        "health_state",
        "image_link",
    ]
    list_filter = ["health_state", "captured_at"]
    search_fields = ["screen__name", "content__url", "error_summary"]
    readonly_fields = [
        "screen",
        "content",
        "image",
        "captured_at",
        "health_state",
        "error_summary",
        "updated_at",
        "image_link",
    ]
    ordering = ["-captured_at", "screen_id", "content_id"]
    date_hierarchy = "captured_at"

    def has_add_permission(self, request):
        return False

    @admin.display(description=_("screenshot"))
    @options(desc=_("Latest diagnostic screenshot"))
    def image_link(self, screenshot):
        if not screenshot.image:
            return _("none")
        return format_html(
            '<a href="{}" target="_blank">View screenshot</a>',
            screenshot.image.url,
        )
