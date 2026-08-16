from django.contrib import admin

from ..models import (
    Content,
    Event,
    Screen,
    ScreenContentScreenshot,
)
from .runtime import EventAdmin, ScreenContentScreenshotAdmin
from .screen import ContentAdmin, ScreenAdmin

admin.site.register(Content, ContentAdmin)
admin.site.register(Event, EventAdmin)
admin.site.register(Screen, ScreenAdmin)
admin.site.register(ScreenContentScreenshot, ScreenContentScreenshotAdmin)
