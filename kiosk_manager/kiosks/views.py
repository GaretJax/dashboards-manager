from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render

from .models import Content, Screen


def screen_display(request, token):
    screen = get_object_or_404(
        Screen.objects.all(),
        public_token=token,
        enabled=True,
    )
    config_url = f"{settings.SITE_BASE_PATH}/api/screens/{token}/config"
    return render(
        request,
        "kiosks/screen.html",
        {
            "screen": screen,
            "config_url": config_url,
        },
    )


def content_content(request, token, content_id):
    content = get_object_or_404(
        Content.objects.filter(
            playlist_entries__screen__public_token=token,
            playlist_entries__screen__enabled=True,
        ),
        pk=content_id,
    )
    if not content.html_file:
        raise Http404("content does not contain an HTML file")
    try:
        with content.html_file.open("rb") as uploaded_file:
            content = uploaded_file.read()
    except OSError as exc:
        raise Http404("HTML file is unavailable") from exc

    # nosemgrep: python.django.security.audit.xss.direct-use-of-httpresponse.direct-use-of-httpresponse
    response = HttpResponse(content, content_type="text/html; charset=utf-8")
    response["Cache-Control"] = "no-store"
    response["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'unsafe-inline'; "
        "script-src 'unsafe-inline'; img-src data:; font-src data:; "
        "object-src 'none'; frame-src 'none'; connect-src 'none'"
    )
    response["X-Content-Type-Options"] = "nosniff"
    response["X-Frame-Options"] = "SAMEORIGIN"
    return response
