from decimal import Decimal, InvalidOperation

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models

import recurrence.fields


def copy_preload_delays(apps, schema_editor):
    del schema_editor
    screen_model = apps.get_model("kiosks", "Screen")
    page_model = apps.get_model("kiosks", "Page")

    for screen in screen_model.objects.all().iterator():
        raw = screen.preload_seconds
        try:
            delay = Decimal(str(raw))
            if not delay.is_finite() or delay < 0:
                raise InvalidOperation
        except InvalidOperation, TypeError, ValueError:
            delay = Decimal("0")
        screen.preload_delay_seconds = delay
        screen.save(update_fields=["preload_delay_seconds"])

    for page in page_model.objects.all().iterator():
        raw = page.preload_seconds
        if raw in (None, "", "auto", "false"):
            delay = None
        else:
            try:
                delay = Decimal(str(raw))
                if not delay.is_finite() or delay < 0:
                    raise InvalidOperation
            except InvalidOperation, TypeError, ValueError:
                delay = None
        page.preload_delay_seconds = delay
        page.save(update_fields=["preload_delay_seconds"])


class Migration(migrations.Migration):
    dependencies = [
        ("kiosks", "0002_screen_preload_settings"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="ScreenURL",
            new_name="Page",
        ),
        migrations.AddField(
            model_name="screen",
            name="off_schedule",
            field=recurrence.fields.RecurrenceField(
                blank=True,
                default="",
                help_text=(
                    "Optional recurring times when screen should receive "
                    "HDMI-CEC standby command. Times use the server timezone."
                ),
                verbose_name="power-off schedule",
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="on_schedule",
            field=recurrence.fields.RecurrenceField(
                blank=True,
                default="",
                help_text=(
                    "Optional recurring times when screen should receive "
                    "HDMI-CEC on command. Times use the server timezone."
                ),
                verbose_name="power-on schedule",
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="preload_delay_seconds",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0"),
                help_text=(
                    "Start loading this many seconds before page display. "
                    "Zero starts loading at the display transition."
                ),
                max_digits=8,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="preload delay (seconds)",
            ),
        ),
        migrations.AddField(
            model_name="page",
            name="html_file",
            field=models.FileField(
                blank=True,
                default="",
                help_text=(
                    "Upload one self-contained HTML file instead of a URL."
                ),
                upload_to="pages/",
                validators=[
                    django.core.validators.FileExtensionValidator(
                        ["html", "htm"]
                    )
                ],
                verbose_name="HTML file",
            ),
        ),
        migrations.AddField(
            model_name="page",
            name="preload_delay_seconds",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text=(
                    "Leave blank to inherit screen setting; otherwise start "
                    "loading this many seconds before display."
                ),
                max_digits=8,
                null=True,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="preload delay override (seconds)",
            ),
        ),
        migrations.RunPython(copy_preload_delays, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="screen",
            name="preload_timeout_seconds",
            field=models.PositiveIntegerField(
                default=30,
                help_text=(
                    "Maximum seconds from navigation request before displaying "
                    "page, even if loading has not completed or preload delay "
                    "remains."
                ),
                validators=[django.core.validators.MinValueValidator(1)],
                verbose_name="preload timeout (seconds)",
            ),
        ),
        migrations.AlterField(
            model_name="page",
            name="screen",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="pages",
                to="kiosks.screen",
                verbose_name="screen",
            ),
        ),
        migrations.AlterField(
            model_name="page",
            name="url",
            field=models.URLField(
                blank=True,
                default="",
                max_length=2048,
                verbose_name="URL",
            ),
        ),
        migrations.AlterField(
            model_name="page",
            name="preload_timeout_seconds",
            field=models.PositiveIntegerField(
                blank=True,
                help_text=(
                    "Leave blank to inherit screen setting; maximum seconds "
                    "from request before displaying page regardless of loading "
                    "state."
                ),
                null=True,
                validators=[django.core.validators.MinValueValidator(1)],
                verbose_name="preload timeout override (seconds)",
            ),
        ),
        migrations.AlterModelOptions(
            name="page",
            options={
                "ordering": ["order", "pk"],
                "verbose_name": "page",
                "verbose_name_plural": "pages",
            },
        ),
        migrations.RemoveConstraint(
            model_name="page",
            name="kiosks_screen_url_order_unique",
        ),
        migrations.RemoveField(
            model_name="screen",
            name="preload_seconds",
        ),
        migrations.RemoveField(
            model_name="page",
            name="preload_seconds",
        ),
        migrations.AddConstraint(
            model_name="page",
            constraint=models.UniqueConstraint(
                fields=("screen", "order"),
                name="kiosks_page_order_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="page",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(models.Q(("url__gt", ""), ("html_file", "")))
                    | models.Q(models.Q(("url", ""), ("html_file__gt", "")))
                ),
                name="kiosks_page_url_xor_html",
            ),
        ),
    ]
