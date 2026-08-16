import re

from django.conf import settings
from django.contrib import admin
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import include, path, re_path
from django.views.static import serve

from .api import api

admin.site.site_header = settings.ADMIN_SITE_HEADER
admin.site.site_title = settings.ADMIN_SITE_TITLE
admin.site.index_title = settings.ADMIN_INDEX_TITLE


def health(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("", lambda request: redirect("admin:index"), name="root"),
    path("health/", health, name="health"),
    path("api/", api.urls),
    path("admin/", admin.site.urls),
    path("", include("kiosk_manager.kiosks.urls")),
]

if settings.ENVIRONMENT in {"local", "test"}:
    media_url_pattern = (
        rf"^{re.escape(settings.MEDIA_URL.lstrip('/'))}(?P<path>.*)$"
    )
    urlpatterns += [
        re_path(
            media_url_pattern,
            serve,
            {"document_root": settings.MEDIA_ROOT},
        )
    ]
