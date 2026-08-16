from django.contrib import admin

from ..models import Content, Event, Screen
from .runtime import EventAdmin
from .screen import ContentAdmin, ScreenAdmin

admin.site.register(Content, ContentAdmin)
admin.site.register(Event, EventAdmin)
admin.site.register(Screen, ScreenAdmin)
