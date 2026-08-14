import django.core.validators
from django.db import migrations, models

import kiosk_manager.kiosks.models


class Migration(migrations.Migration):
    dependencies = [
        ("kiosks", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="screen",
            name="preload_seconds",
            field=models.CharField(
                default="auto",
                help_text=(
                    "auto waits for loadEventFired; false disables "
                    "preloading; otherwise enter seconds"
                ),
                max_length=32,
                validators=[
                    kiosk_manager.kiosks.models.validate_preload_seconds
                ],
                verbose_name="preload seconds",
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="preload_timeout_seconds",
            field=models.PositiveIntegerField(
                default=30,
                validators=[django.core.validators.MinValueValidator(1)],
                verbose_name="preload timeout (seconds)",
            ),
        ),
        migrations.AddField(
            model_name="screenurl",
            name="preload_seconds",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "leave blank to inherit screen setting; use auto, false, "
                    "or seconds"
                ),
                max_length=32,
                validators=[
                    kiosk_manager.kiosks.models.validate_preload_seconds
                ],
                verbose_name="preload seconds override",
            ),
        ),
        migrations.AddField(
            model_name="screenurl",
            name="preload_timeout_seconds",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                validators=[django.core.validators.MinValueValidator(1)],
                verbose_name="preload timeout override (seconds)",
            ),
        ),
    ]
