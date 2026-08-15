import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("kiosks", "0003_page_schedule_and_preload"),
    ]

    operations = [
        migrations.AddField(
            model_name="screen",
            name="power_override",
            field=models.CharField(
                blank=True,
                choices=[("on", "on"), ("off", "off")],
                default="",
                help_text="Temporary on/off override. Clear to follow configured schedule.",
                max_length=16,
                verbose_name="temporary power override",
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="reported_power_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="reported power at"
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="reported_power_state",
            field=models.CharField(
                choices=[("on", "on"), ("off", "off"), ("unknown", "unknown")],
                default="unknown",
                help_text="Last power state reported by kiosk agent.",
                max_length=16,
                verbose_name="reported power state",
            ),
        ),
        migrations.CreateModel(
            name="ScreenCommand",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                        verbose_name="id",
                    ),
                ),
                (
                    "command",
                    models.CharField(
                        choices=[("restart_agent", "restart agent")],
                        max_length=32,
                        verbose_name="command",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="created at"
                    ),
                ),
                (
                    "acknowledged_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="acknowledged at"
                    ),
                ),
                (
                    "screen",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="commands",
                        to="kiosks.screen",
                        verbose_name="screen",
                    ),
                ),
            ],
            options={
                "verbose_name": "screen command",
                "verbose_name_plural": "screen commands",
                "ordering": ["-created_at", "id"],
            },
        ),
    ]
