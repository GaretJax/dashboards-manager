from django.conf import settings
from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from adminutils import ModelAdmin, object_action, options

from ..models import ScreenURL


class ScreenURLInline(admin.TabularInline):
    model = ScreenURL
    extra = 1
    fields = [
        "order",
        "url",
        "duration_seconds",
        "preload_seconds",
        "preload_timeout_seconds",
    ]
    ordering = ["order", "pk"]
    verbose_name = _("screen URL")
    verbose_name_plural = _("screen URLs")


class ScreenAdmin(ModelAdmin):
    fieldsets = [
        (
            _("Screen"),
            {
                "fields": [
                    "id",
                    "name",
                    "enabled",
                ],
            },
        ),
        (
            _("Preloading"),
            {
                "fields": [
                    "preload_seconds",
                    "preload_timeout_seconds",
                ],
            },
        ),
        (
            _("Public access"),
            {
                "fields": [
                    "public_token",
                    "display_url",
                ],
            },
        ),
        (
            _("Timestamps"),
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
    search_fields = ["name", "public_token", "screen_urls__url"]
    readonly_fields = [
        "id",
        "public_token",
        "display_url",
        "created_at",
        "updated_at",
    ]
    ordering = ["name", "pk"]
    date_hierarchy = "created_at"
    inlines = [ScreenURLInline]
    change_actions = ["rotate_public_token_action"]

    @admin.display(description=_("display URL"))
    @options(desc=_("Public URL for this screen"))
    def display_url(self, screen):
        display_url = (
            f"{settings.SITE_BASE_PATH}/screens/{screen.public_token}/"
        )
        return format_html('<a href="{0}">{0}</a>', display_url)

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
