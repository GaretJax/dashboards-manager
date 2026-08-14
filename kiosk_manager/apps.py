from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class DefaultConfig(AppConfig):
    name = "kiosk_manager"
    verbose_name = _("Kiosk Manager")
