import django.db.models.deletion
from django.db import migrations, models


def copy_runtime_status(apps, schema_editor):
    Screen = apps.get_model("kiosks", "Screen")
    RuntimeStatus = apps.get_model("kiosks", "ScreenRuntimeStatus")

    for screen in Screen.objects.all().iterator():
        screen.status_power_state = screen.reported_power_state
        screen.status_power_at = screen.reported_power_at
        screen.status_created_at = None
        screen.status_updated_at = None
        screen.save(
            update_fields=[
                "status_power_state",
                "status_power_at",
                "status_created_at",
                "status_updated_at",
            ]
        )

    status_fields = [
        "status_agent_version",
        "status_browser_version",
        "status_agent_started_at",
        "status_uptime_seconds",
        "status_last_check_in",
        "status_health_state",
        "status_health_error",
        "status_load_1m",
        "status_load_5m",
        "status_load_15m",
        "status_memory_total_bytes",
        "status_memory_used_bytes",
        "status_memory_available_bytes",
        "status_memory_percent",
        "status_current_content",
        "status_last_successful_page_load_at",
        "status_display_identity",
        "status_display_width",
        "status_display_height",
        "status_display_refresh_rate",
        "status_display_orientation",
        "status_browser_error",
        "status_display_error",
        "status_created_at",
        "status_updated_at",
    ]
    for status in RuntimeStatus.objects.select_related("screen").iterator():
        screen = status.screen
        values = {
            "status_agent_version": status.agent_version,
            "status_browser_version": status.browser_version,
            "status_agent_started_at": status.agent_started_at,
            "status_uptime_seconds": status.uptime_seconds,
            "status_last_check_in": status.last_check_in,
            "status_health_state": status.health_state,
            "status_health_error": status.health_error,
            "status_load_1m": status.load_1m,
            "status_load_5m": status.load_5m,
            "status_load_15m": status.load_15m,
            "status_memory_total_bytes": status.memory_total_bytes,
            "status_memory_used_bytes": status.memory_used_bytes,
            "status_memory_available_bytes": status.memory_available_bytes,
            "status_memory_percent": status.memory_percent,
            "status_current_content_id": status.current_content_id,
            "status_last_successful_page_load_at": (
                status.last_successful_page_load_at
            ),
            "status_display_identity": status.display_identity,
            "status_display_width": status.display_width,
            "status_display_height": status.display_height,
            "status_display_refresh_rate": status.display_refresh_rate,
            "status_display_orientation": status.display_orientation,
            "status_browser_error": status.browser_error,
            "status_display_error": status.display_error,
            "status_created_at": status.created_at,
            "status_updated_at": status.updated_at,
        }
        if status.actual_power_state:
            values["status_power_state"] = status.actual_power_state
        for field, value in values.items():
            setattr(screen, field, value)
        screen.save(update_fields=[*status_fields, "status_power_state"])


def restore_runtime_status(apps, schema_editor):
    Screen = apps.get_model("kiosks", "Screen")
    RuntimeStatus = apps.get_model("kiosks", "ScreenRuntimeStatus")

    for screen in Screen.objects.all().iterator():
        RuntimeStatus.objects.create(
            screen=screen,
            agent_version=screen.status_agent_version,
            browser_version=screen.status_browser_version,
            agent_started_at=screen.status_agent_started_at,
            uptime_seconds=screen.status_uptime_seconds,
            last_check_in=screen.status_last_check_in,
            health_state=screen.status_health_state,
            health_error=screen.status_health_error,
            load_1m=screen.status_load_1m,
            load_5m=screen.status_load_5m,
            load_15m=screen.status_load_15m,
            memory_total_bytes=screen.status_memory_total_bytes,
            memory_used_bytes=screen.status_memory_used_bytes,
            memory_available_bytes=screen.status_memory_available_bytes,
            memory_percent=screen.status_memory_percent,
            current_content_id=screen.status_current_content_id,
            last_successful_page_load_at=(
                screen.status_last_successful_page_load_at
            ),
            desired_power_state="",
            actual_power_state=screen.status_power_state,
            display_identity=screen.status_display_identity,
            display_width=screen.status_display_width,
            display_height=screen.status_display_height,
            display_refresh_rate=screen.status_display_refresh_rate,
            display_orientation=screen.status_display_orientation,
            browser_error=screen.status_browser_error,
            display_error=screen.status_display_error,
            created_at=screen.status_created_at,
            updated_at=screen.status_updated_at,
        )
        screen.reported_power_state = screen.status_power_state
        screen.reported_power_at = screen.status_power_at
        screen.save(
            update_fields=["reported_power_state", "reported_power_at"]
        )


class Migration(migrations.Migration):
    dependencies = [
        ("kiosks", "0013_alter_screencommand_command"),
    ]

    operations = [
        migrations.AddField(
            model_name="screen",
            name="status_agent_started_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="status agent started at"
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="status_agent_version",
            field=models.CharField(
                blank=True, max_length=64, verbose_name="status agent version"
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="status_browser_error",
            field=models.TextField(
                blank=True, verbose_name="status browser error"
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="status_browser_version",
            field=models.CharField(
                blank=True,
                max_length=256,
                verbose_name="status browser version",
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="status_created_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="screen",
            name="status_current_content",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="status_screens",
                to="kiosks.content",
                verbose_name="status current content",
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="status_display_error",
            field=models.TextField(
                blank=True, verbose_name="status display error"
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="status_display_height",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="status display height"
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="status_display_identity",
            field=models.CharField(
                blank=True,
                max_length=128,
                verbose_name="status display identity",
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="status_display_orientation",
            field=models.CharField(
                blank=True,
                max_length=32,
                verbose_name="status display orientation",
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="status_display_refresh_rate",
            field=models.FloatField(
                blank=True,
                null=True,
                verbose_name="status display refresh rate",
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="status_display_width",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="status display width"
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="status_health_error",
            field=models.TextField(
                blank=True, verbose_name="status health error"
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="status_health_state",
            field=models.CharField(
                choices=[
                    ("unknown", "unknown"),
                    ("healthy", "healthy"),
                    ("degraded", "degraded"),
                    ("error", "error"),
                ],
                default="unknown",
                max_length=16,
                verbose_name="status health state",
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="status_last_check_in",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="status last check-in"
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="status_last_successful_page_load_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="status last successful page load at",
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="status_load_15m",
            field=models.FloatField(
                blank=True,
                null=True,
                verbose_name="status fifteen-minute load",
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="status_load_1m",
            field=models.FloatField(
                blank=True, null=True, verbose_name="status one-minute load"
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="status_load_5m",
            field=models.FloatField(
                blank=True, null=True, verbose_name="status five-minute load"
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="status_memory_available_bytes",
            field=models.BigIntegerField(
                blank=True,
                null=True,
                verbose_name="status memory available (bytes)",
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="status_memory_percent",
            field=models.FloatField(
                blank=True,
                null=True,
                verbose_name="status memory used (percent)",
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="status_memory_total_bytes",
            field=models.BigIntegerField(
                blank=True,
                null=True,
                verbose_name="status memory total (bytes)",
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="status_memory_used_bytes",
            field=models.BigIntegerField(
                blank=True,
                null=True,
                verbose_name="status memory used (bytes)",
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="status_power_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="status power at"
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="status_power_state",
            field=models.CharField(
                choices=[("on", "on"), ("off", "off"), ("unknown", "unknown")],
                default="unknown",
                help_text="Last power state reported by kiosk agent.",
                max_length=16,
                verbose_name="status power state",
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="status_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="screen",
            name="status_uptime_seconds",
            field=models.FloatField(
                blank=True, null=True, verbose_name="status uptime (seconds)"
            ),
        ),
        migrations.RunPython(copy_runtime_status, restore_runtime_status),
        migrations.RemoveField(
            model_name="screen",
            name="reported_power_at",
        ),
        migrations.RemoveField(
            model_name="screen",
            name="reported_power_state",
        ),
        migrations.RemoveIndex(
            model_name="screenruntimestatus",
            name="kiosks_status_health_check",
        ),
        migrations.DeleteModel(
            name="ScreenRuntimeStatus",
        ),
    ]
