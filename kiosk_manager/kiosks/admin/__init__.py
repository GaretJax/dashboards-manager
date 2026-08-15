from django.contrib import admin

from ..models import Content, Screen
from .screen import ContentAdmin, ScreenAdmin

admin.site.register(Content, ContentAdmin)
admin.site.register(Screen, ScreenAdmin)
