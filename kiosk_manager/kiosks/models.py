import secrets

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


def generate_public_token():
    return secrets.token_urlsafe(32)


class Screen(models.Model):
    name = models.CharField(_("name"), max_length=200)
    public_token = models.CharField(
        _("public token"),
        max_length=64,
        unique=True,
        default=generate_public_token,
        editable=False,
    )
    enabled = models.BooleanField(
        _("enabled"),
        default=True,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = _("screen")
        verbose_name_plural = _("screens")

    def __str__(self):
        return str(self.name)

    def rotate_public_token(self):
        self.public_token = generate_public_token()
        self.save(update_fields=["public_token", "updated_at"])


class ScreenURL(models.Model):
    screen = models.ForeignKey(
        Screen,
        verbose_name=_("screen"),
        related_name="screen_urls",
        on_delete=models.CASCADE,
    )
    url = models.URLField(_("URL"), max_length=2048)
    duration_seconds = models.PositiveIntegerField(
        _("time on screen (seconds)"),
        validators=[MinValueValidator(1)],
        default=30,
    )
    order = models.PositiveIntegerField(
        _("order"),
        validators=[MinValueValidator(1)],
        default=1,
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        ordering = ["order", "pk"]
        verbose_name = _("screen URL")
        verbose_name_plural = _("screen URLs")
        constraints = [
            models.UniqueConstraint(
                fields=["screen", "order"],
                name="kiosks_screen_url_order_unique",
            )
        ]

    def __str__(self):
        return f"{self.screen} · {self.order} · {self.url}"
