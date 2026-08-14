from django.urls import path

from . import views

app_name = "kiosks"

urlpatterns = [
    path(
        "screens/<str:token>/",
        views.screen_display,
        name="screen-display",
    ),
]
