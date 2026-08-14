from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class KiosksConfig(AppConfig):
    name = "kiosk_manager.kiosks"
    verbose_name = _("Kiosks")
