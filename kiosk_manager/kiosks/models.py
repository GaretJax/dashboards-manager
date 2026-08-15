import secrets
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from recurrence.fields import RecurrenceField

DEFAULT_PRELOAD_DELAY_SECONDS = Decimal("0")
DEFAULT_PRELOAD_TIMEOUT_SECONDS = 30


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
    on_schedule = RecurrenceField(
        include_dtstart=False,
        blank=True,
        default="",
        verbose_name=_("power-on schedule"),
        help_text=_(
            "Optional recurring times when screen should receive HDMI-CEC "
            "on command. Times use the server timezone."
        ),
    )
    off_schedule = RecurrenceField(
        include_dtstart=False,
        blank=True,
        default="",
        verbose_name=_("power-off schedule"),
        help_text=_(
            "Optional recurring times when screen should receive HDMI-CEC "
            "standby command. Times use the server timezone."
        ),
    )
    preload_delay_seconds = models.DecimalField(
        _("preload delay (seconds)"),
        max_digits=8,
        decimal_places=2,
        default=DEFAULT_PRELOAD_DELAY_SECONDS,
        validators=[MinValueValidator(0)],
        help_text=_(
            "Start loading this many seconds before page display. "
            "Zero starts loading at the display transition."
        ),
    )
    preload_timeout_seconds = models.PositiveIntegerField(
        _("preload timeout (seconds)"),
        default=DEFAULT_PRELOAD_TIMEOUT_SECONDS,
        validators=[MinValueValidator(1)],
        help_text=_(
            "Maximum seconds from navigation request before displaying page, "
            "even if loading has not completed or preload delay remains."
        ),
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


class Page(models.Model):
    screen = models.ForeignKey(
        Screen,
        verbose_name=_("screen"),
        related_name="pages",
        on_delete=models.CASCADE,
    )
    url = models.URLField(
        _("URL"),
        max_length=2048,
        blank=True,
        default="",
    )
    html_file = models.FileField(
        _("HTML file"),
        upload_to="pages/",
        blank=True,
        default="",
        validators=[FileExtensionValidator(["html", "htm"])],
        help_text=_("Upload one self-contained HTML file instead of a URL."),
    )
    duration_seconds = models.PositiveIntegerField(
        _("time on screen (seconds)"),
        validators=[MinValueValidator(1)],
        default=30,
    )
    preload_delay_seconds = models.DecimalField(
        _("preload delay override (seconds)"),
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(0)],
        help_text=_(
            "Leave blank to inherit screen setting; otherwise start loading "
            "this many seconds before display."
        ),
    )
    preload_timeout_seconds = models.PositiveIntegerField(
        _("preload timeout override (seconds)"),
        blank=True,
        null=True,
        validators=[MinValueValidator(1)],
        help_text=_(
            "Leave blank to inherit screen setting; maximum seconds from "
            "request before displaying page regardless of loading state."
        ),
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
        verbose_name = _("page")
        verbose_name_plural = _("pages")
        constraints = [
            models.UniqueConstraint(
                fields=["screen", "order"],
                name="kiosks_page_order_unique",
            ),
            models.CheckConstraint(
                condition=(
                    (models.Q(url__gt="") & models.Q(html_file=""))
                    | (models.Q(url="") & models.Q(html_file__gt=""))
                ),
                name="kiosks_page_url_xor_html",
            ),
        ]

    def __str__(self):
        source = self.url or self.html_file.name or _("HTML page")
        return f"{self.screen} · {self.order} · {source}"

    def clean(self):
        super().clean()
        has_url = bool(self.url)
        has_html = bool(self.html_file)
        if has_url == has_html:
            raise ValidationError(
                {
                    "url": _("Provide URL or HTML file, not both."),
                    "html_file": _("Provide URL or HTML file, not both."),
                }
            )
