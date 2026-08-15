import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("kiosks", "0006_content_injected_css_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ScreenContentScreenshot",
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
                    "image",
                    models.FileField(
                        upload_to="screenshots/", verbose_name="screenshot"
                    ),
                ),
                (
                    "captured_at",
                    models.DateTimeField(verbose_name="captured at"),
                ),
                (
                    "health_state",
                    models.CharField(
                        choices=[
                            ("unknown", "unknown"),
                            ("healthy", "healthy"),
                            ("degraded", "degraded"),
                            ("error", "error"),
                        ],
                        default="unknown",
                        max_length=16,
                        verbose_name="health state",
                    ),
                ),
                (
                    "error_summary",
                    models.TextField(blank=True, verbose_name="error summary"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="updated at"
                    ),
                ),
                (
                    "content",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="screenshots",
                        to="kiosks.content",
                        verbose_name="content",
                    ),
                ),
                (
                    "screen",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="content_screenshots",
                        to="kiosks.screen",
                        verbose_name="screen",
                    ),
                ),
            ],
            options={
                "verbose_name": "screen content screenshot",
                "verbose_name_plural": "screen content screenshots",
                "ordering": ["-captured_at", "screen_id", "content_id"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("screen", "content"),
                        name="kiosks_screenshot_screen_content_unique",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="ScreenRuntimeStatus",
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
                    "agent_version",
                    models.CharField(
                        blank=True, max_length=64, verbose_name="agent version"
                    ),
                ),
                (
                    "browser_version",
                    models.CharField(
                        blank=True,
                        max_length=256,
                        verbose_name="browser version",
                    ),
                ),
                (
                    "agent_started_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="agent started at"
                    ),
                ),
                (
                    "uptime_seconds",
                    models.FloatField(
                        blank=True, null=True, verbose_name="uptime (seconds)"
                    ),
                ),
                (
                    "last_check_in",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="last check-in"
                    ),
                ),
                (
                    "health_state",
                    models.CharField(
                        choices=[
                            ("unknown", "unknown"),
                            ("healthy", "healthy"),
                            ("degraded", "degraded"),
                            ("error", "error"),
                        ],
                        default="unknown",
                        max_length=16,
                        verbose_name="health state",
                    ),
                ),
                (
                    "health_error",
                    models.TextField(blank=True, verbose_name="health error"),
                ),
                (
                    "load_1m",
                    models.FloatField(
                        blank=True, null=True, verbose_name="one-minute load"
                    ),
                ),
                (
                    "load_5m",
                    models.FloatField(
                        blank=True, null=True, verbose_name="five-minute load"
                    ),
                ),
                (
                    "load_15m",
                    models.FloatField(
                        blank=True,
                        null=True,
                        verbose_name="fifteen-minute load",
                    ),
                ),
                (
                    "memory_total_bytes",
                    models.BigIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="memory total (bytes)",
                    ),
                ),
                (
                    "memory_used_bytes",
                    models.BigIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="memory used (bytes)",
                    ),
                ),
                (
                    "memory_available_bytes",
                    models.BigIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="memory available (bytes)",
                    ),
                ),
                (
                    "memory_percent",
                    models.FloatField(
                        blank=True,
                        null=True,
                        verbose_name="memory used (percent)",
                    ),
                ),
                (
                    "last_successful_page_load_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="last successful page load at",
                    ),
                ),
                (
                    "desired_power_state",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("on", "on"),
                            ("off", "off"),
                            ("unknown", "unknown"),
                        ],
                        default="",
                        max_length=16,
                        verbose_name="desired power state",
                    ),
                ),
                (
                    "actual_power_state",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("on", "on"),
                            ("off", "off"),
                            ("unknown", "unknown"),
                        ],
                        default="",
                        max_length=16,
                        verbose_name="actual power state",
                    ),
                ),
                (
                    "display_identity",
                    models.CharField(
                        blank=True,
                        max_length=128,
                        verbose_name="display identity",
                    ),
                ),
                (
                    "display_width",
                    models.PositiveIntegerField(
                        blank=True, null=True, verbose_name="display width"
                    ),
                ),
                (
                    "display_height",
                    models.PositiveIntegerField(
                        blank=True, null=True, verbose_name="display height"
                    ),
                ),
                (
                    "display_refresh_rate",
                    models.FloatField(
                        blank=True,
                        null=True,
                        verbose_name="display refresh rate",
                    ),
                ),
                (
                    "display_orientation",
                    models.CharField(
                        blank=True,
                        max_length=32,
                        verbose_name="display orientation",
                    ),
                ),
                (
                    "browser_error",
                    models.TextField(blank=True, verbose_name="browser error"),
                ),
                (
                    "display_error",
                    models.TextField(blank=True, verbose_name="display error"),
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
                    "current_content",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="runtime_statuses",
                        to="kiosks.content",
                        verbose_name="current content",
                    ),
                ),
                (
                    "screen",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="runtime_status",
                        to="kiosks.screen",
                        verbose_name="screen",
                    ),
                ),
            ],
            options={
                "verbose_name": "screen runtime status",
                "verbose_name_plural": "screen runtime statuses",
                "ordering": ["-last_check_in", "screen_id"],
                "indexes": [
                    models.Index(
                        fields=["health_state", "last_check_in"],
                        name="kiosks_status_health_check",
                    )
                ],
            },
        ),
    ]
