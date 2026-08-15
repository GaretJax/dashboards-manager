from django.contrib import admin

from ..models import (
    Content,
    Screen,
    ScreenContentScreenshot,
    ScreenRuntimeStatus,
)
from .runtime import ScreenContentScreenshotAdmin, ScreenRuntimeStatusAdmin
from .screen import ContentAdmin, ScreenAdmin

admin.site.register(Content, ContentAdmin)
admin.site.register(Screen, ScreenAdmin)
admin.site.register(ScreenRuntimeStatus, ScreenRuntimeStatusAdmin)
admin.site.register(ScreenContentScreenshot, ScreenContentScreenshotAdmin)
