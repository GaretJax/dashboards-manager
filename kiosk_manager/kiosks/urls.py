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
        "screens/<str:token>/pages/<int:page_id>/",
        views.page_content,
        name="page-content",
    ),
]
