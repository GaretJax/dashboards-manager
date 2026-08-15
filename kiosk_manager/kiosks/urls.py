from django.urls import path

from . import views

app_name = "kiosks"

urlpatterns = [
    path(
        "screens/<str:token>/",
        views.screen_display,
        name="screen-display",
    ),
    path(
        "screens/<str:token>/contents/<int:content_id>/",
        views.content_content,
        name="content-content",
    ),
]
