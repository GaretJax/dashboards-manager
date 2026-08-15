from django.urls import path

from . import views

app_name = "kiosks"

urlpatterns = [
    path("install.sh", views.agent_install, name="agent-install"),
    path(
        "downloads/kiosk-agent.whl",
        views.agent_wheel_redirect,
        name="agent-wheel",
    ),
    path(
        "downloads/<str:filename>",
        views.agent_wheel_download,
        name="agent-wheel-versioned",
    ),
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
