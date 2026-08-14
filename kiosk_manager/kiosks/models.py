import secrets
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

PRELOAD_AUTO = "auto"
PRELOAD_DISABLED = "false"
PRELOAD_INHERIT = ""
DEFAULT_PRELOAD_TIMEOUT_SECONDS = 30


def generate_public_token():
    return secrets.token_urlsafe(32)


def validate_preload_seconds(value):
    if value in {PRELOAD_INHERIT, PRELOAD_AUTO, PRELOAD_DISABLED}:
        return
    try:
        seconds = Decimal(str(value))
    except InvalidOperation, ValueError:
        raise ValidationError(
            "Enter auto, false, or a non-negative number of seconds."
        ) from None
    if not seconds.is_finite() or seconds < 0:
        raise ValidationError(
            "Enter auto, false, or a non-negative number of seconds."
        )


def serialize_preload_seconds(value):
    if value == PRELOAD_AUTO:
        return PRELOAD_AUTO
    if value == PRELOAD_DISABLED:
        return False
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("invalid preload_seconds") from exc


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
    preload_seconds = models.CharField(
        _("preload seconds"),
        max_length=32,
        default=PRELOAD_AUTO,
        validators=[validate_preload_seconds],
        help_text=_(
            "auto waits for loadEventFired; false disables preloading; "
            "otherwise enter seconds"
        ),
    )
    preload_timeout_seconds = models.PositiveIntegerField(
        _("preload timeout (seconds)"),
        default=DEFAULT_PRELOAD_TIMEOUT_SECONDS,
        validators=[MinValueValidator(1)],
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
    preload_seconds = models.CharField(
        _("preload seconds override"),
        max_length=32,
        default=PRELOAD_INHERIT,
        blank=True,
        validators=[validate_preload_seconds],
        help_text=_(
            "leave blank to inherit screen setting; use auto, false, or "
            "seconds"
        ),
    )
    preload_timeout_seconds = models.PositiveIntegerField(
        _("preload timeout override (seconds)"),
        blank=True,
        null=True,
        validators=[MinValueValidator(1)],
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
