from django.db import migrations, models


def copy_screenshots(apps, schema_editor):
    ScreenContent = apps.get_model("kiosks", "ScreenContent")
    Screenshot = apps.get_model("kiosks", "ScreenContentScreenshot")

    for screenshot in Screenshot.objects.all().iterator():
        screen_content = (
            ScreenContent.objects.filter(
                screen_id=screenshot.screen_id,
                content_id=screenshot.content_id,
            )
            .order_by("pk")
            .first()
        )
        if screen_content is None:
            continue
        screen_content.screenshot_image = screenshot.image.name
        screen_content.screenshot_captured_at = screenshot.captured_at
        screen_content.screenshot_health_state = screenshot.health_state
        screen_content.screenshot_error_summary = screenshot.error_summary
        screen_content.screenshot_updated_at = screenshot.updated_at
        screen_content.save(
            update_fields=[
                "screenshot_image",
                "screenshot_captured_at",
                "screenshot_health_state",
                "screenshot_error_summary",
                "screenshot_updated_at",
            ]
        )


def restore_screenshots(apps, schema_editor):
    ScreenContent = apps.get_model("kiosks", "ScreenContent")
    Screenshot = apps.get_model("kiosks", "ScreenContentScreenshot")

    for screen_content in ScreenContent.objects.exclude(
        screenshot_image=""
    ).iterator():
        if screen_content.screenshot_captured_at is None:
            continue
        Screenshot.objects.create(
            screen_id=screen_content.screen_id,
            content_id=screen_content.content_id,
            image=screen_content.screenshot_image.name,
            captured_at=screen_content.screenshot_captured_at,
            health_state=screen_content.screenshot_health_state,
            error_summary=screen_content.screenshot_error_summary,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("kiosks", "0014_screen_status_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="screencontent",
            name="screenshot_captured_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="screenshot captured at",
            ),
        ),
        migrations.AddField(
            model_name="screencontent",
            name="screenshot_error_summary",
            field=models.TextField(
                blank=True,
                verbose_name="screenshot error summary",
            ),
        ),
        migrations.AddField(
            model_name="screencontent",
            name="screenshot_health_state",
            field=models.CharField(
                choices=[
                    ("unknown", "unknown"),
                    ("healthy", "healthy"),
                    ("degraded", "degraded"),
                    ("error", "error"),
                ],
                default="unknown",
                max_length=16,
                verbose_name="screenshot health state",
            ),
        ),
        migrations.AddField(
            model_name="screencontent",
            name="screenshot_image",
            field=models.FileField(
                blank=True,
                default="",
                upload_to="screenshots/",
                verbose_name="screenshot",
            ),
        ),
        migrations.AddField(
            model_name="screencontent",
            name="screenshot_updated_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="screenshot updated at",
            ),
        ),
        migrations.RunPython(copy_screenshots, restore_screenshots),
        migrations.RemoveConstraint(
            model_name="screencontentscreenshot",
            name="kiosks_screenshot_screen_content_unique",
        ),
        migrations.DeleteModel(
            name="ScreenContentScreenshot",
        ),
    ]
