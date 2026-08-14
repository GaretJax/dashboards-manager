from django.contrib import admin

from ..models import Screen
from .screen import ScreenAdmin

admin.site.register(Screen, ScreenAdmin)
