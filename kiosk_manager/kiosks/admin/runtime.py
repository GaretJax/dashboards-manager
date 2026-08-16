from adminutils import ModelAdmin

from ..models import Event


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
