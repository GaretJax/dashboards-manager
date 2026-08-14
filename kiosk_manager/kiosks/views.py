from django.conf import settings
from django.shortcuts import get_object_or_404, render

from .models import Screen


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
