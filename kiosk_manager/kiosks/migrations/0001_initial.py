import django.core.validators
import django.db.models.deletion
from django.db import migrations, models

import kiosk_manager.kiosks.models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Screen",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "name",
                    models.CharField(max_length=200, verbose_name="name"),
                ),
                (
                    "public_token",
                    models.CharField(
                        default=kiosk_manager.kiosks.models.generate_public_token,
                        editable=False,
                        max_length=64,
                        unique=True,
                        verbose_name="public token",
                    ),
                ),
                (
                    "enabled",
                    models.BooleanField(default=True, verbose_name="enabled"),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="created at"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="updated at"
                    ),
                ),
            ],
            options={
                "verbose_name": "screen",
                "verbose_name_plural": "screens",
                "ordering": ["name", "pk"],
            },
        ),
        migrations.CreateModel(
            name="ScreenURL",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "url",
                    models.URLField(max_length=2048, verbose_name="URL"),
                ),
                (
                    "duration_seconds",
                    models.PositiveIntegerField(
                        default=30,
                        validators=[
                            django.core.validators.MinValueValidator(1)
                        ],
                        verbose_name="time on screen (seconds)",
                    ),
                ),
                (
                    "order",
                    models.PositiveIntegerField(
                        default=1,
                        validators=[
                            django.core.validators.MinValueValidator(1)
                        ],
                        verbose_name="order",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="created at"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="updated at"
                    ),
                ),
                (
                    "screen",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="screen_urls",
                        to="kiosks.screen",
                        verbose_name="screen",
                    ),
                ),
            ],
            options={
                "verbose_name": "screen URL",
                "verbose_name_plural": "screen URLs",
                "ordering": ["order", "pk"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("screen", "order"),
                        name="kiosks_screen_url_order_unique",
                    )
                ],
            },
        ),
    ]
