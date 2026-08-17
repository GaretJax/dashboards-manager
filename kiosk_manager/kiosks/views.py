import shlex
from pathlib import Path
from urllib.parse import quote, urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.text import slugify

from .agent_package import agent_wheel_path
from .models import Content, Screen, media_format_for_name


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


def agent_wheel_redirect(request):
    wheel = agent_wheel_path()
    location = reverse(
        "kiosks:agent-wheel-versioned",
        kwargs={"filename": wheel.name},
    )
    response = HttpResponse(status=302)
    response["Location"] = location
    response["Cache-Control"] = "no-store"
    return response


def agent_wheel_download(request, filename):
    wheel = agent_wheel_path()
    if Path(filename).name != filename or filename != wheel.name:
        raise Http404("agent wheel is unavailable")
    response = FileResponse(
        wheel.open("rb"),
        as_attachment=True,
        filename=wheel.name,
        content_type="application/octet-stream",
    )
    response["Cache-Control"] = "public, max-age=31536000, immutable"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _manager_base_url(request):
    base_path = settings.SITE_BASE_PATH.strip("/")
    path = f"/{base_path}/" if base_path else "/"
    return request.build_absolute_uri(path).rstrip("/")


def agent_install(request):
    token = request.GET.get("screen", "")
    screen = get_object_or_404(
        Screen.objects.all(),
        public_token=token,
        enabled=True,
    )
    wheel = agent_wheel_path()
    wheel_url = request.build_absolute_uri(
        reverse(
            "kiosks:agent-wheel-versioned",
            kwargs={"filename": wheel.name},
        )
    )
    default_config_name = slugify(screen.name) or f"screen-{screen.pk}"
    script = render_to_string(
        "kiosks/install.sh",
        {
            "manager_url": shlex.quote(_manager_base_url(request)),
            "screen_token": shlex.quote(screen.public_token),
            "wheel_url": shlex.quote(wheel_url),
            "install_url": shlex.quote(request.build_absolute_uri()),
            "default_config_name": shlex.quote(default_config_name),
        },
    )
    response = HttpResponse(script, content_type="text/x-shellscript")
    response["Cache-Control"] = "no-store"
    response["Content-Disposition"] = (
        f'inline; filename="install-{quote(screen.public_token)}.sh"'
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


def content_content(request, token, content_id):
    content = get_object_or_404(
        Content.objects.filter(
            playlist_entries__screen__public_token=token,
            playlist_entries__screen__enabled=True,
        ).distinct(),
        pk=content_id,
    )
    if content.html:
        # nosemgrep: python.django.security.audit.xss.direct-use-of-httpresponse.direct-use-of-httpresponse
        response = HttpResponse(
            content.html,
            content_type="text/html; charset=utf-8",
        )
        response["Cache-Control"] = "no-store"
        response["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'unsafe-inline'; "
            "script-src 'unsafe-inline'; img-src data:; font-src data:; "
            "object-src 'none'; frame-src 'none'; connect-src 'none'"
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["X-Frame-Options"] = "SAMEORIGIN"
        return response
    if not content.media:
        raise Http404("content does not contain HTML or media")
    try:
        media_kind, media_type = media_format_for_name(content.media.name)
        media_url = content.media.url
    except (OSError, ValidationError, ValueError) as exc:
        raise Http404("media file is unavailable") from exc

    media_origin = _media_origin(media_url)
    response = render(
        request,
        "kiosks/content_media.html",
        {
            "content": content,
            "media_kind": media_kind,
            "media_type": media_type,
            "media_url": media_url,
        },
    )
    response["Cache-Control"] = "no-store"
    response["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'unsafe-inline'; "
        f"img-src {media_origin}; media-src {media_origin}; "
        "object-src 'none'; frame-src 'none'; connect-src 'none'"
    )
    response["X-Content-Type-Options"] = "nosniff"
    response["X-Frame-Options"] = "SAMEORIGIN"
    return response


def _media_origin(media_url):
    parsed = urlsplit(media_url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return "'self'"
