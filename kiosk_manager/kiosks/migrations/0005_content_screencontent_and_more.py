from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def copy_pages_to_content(apps, schema_editor):
    del schema_editor
    page_model = apps.get_model("kiosks", "Page")
    content_model = apps.get_model("kiosks", "Content")
    screen_content_model = apps.get_model("kiosks", "ScreenContent")

    for page in page_model.objects.select_related("screen").order_by("pk"):
        delay = page.preload_delay_seconds
        if delay is None:
            delay = page.screen.preload_delay_seconds
        timeout = page.preload_timeout_seconds
        if timeout is None:
            timeout = page.screen.preload_timeout_seconds
        content = content_model.objects.create(
            url=page.url,
            html_file=page.html_file.name,
            preload_delay_seconds=delay,
            preload_timeout_seconds=timeout,
        )
        screen_content_model.objects.create(
            screen_id=page.screen_id,
            content_id=content.pk,
            duration_seconds=page.duration_seconds,
            order=page.order,
        )


class Migration(migrations.Migration):
    dependencies = [
        (
            "kiosks",
            "0004_screen_power_override_screen_reported_power_at_and_more",
        ),
    ]

    operations = [
        migrations.CreateModel(
            name="Content",
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
                    models.URLField(
                        blank=True,
                        default="",
                        max_length=2048,
                        verbose_name="URL",
                    ),
                ),
                (
                    "html_file",
                    models.FileField(
                        blank=True,
                        default="",
                        help_text="Upload one self-contained HTML file instead of a URL.",
                        upload_to="contents/",
                        validators=[
                            django.core.validators.FileExtensionValidator(
                                ["html", "htm"]
                            )
                        ],
                        verbose_name="HTML file",
                    ),
                ),
                (
                    "preload_delay_seconds",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0"),
                        help_text="Start loading this many seconds before display. Zero starts loading at the display transition.",
                        max_digits=8,
                        validators=[
                            django.core.validators.MinValueValidator(0)
                        ],
                        verbose_name="preload delay (seconds)",
                    ),
                ),
                (
                    "preload_timeout_seconds",
                    models.PositiveIntegerField(
                        default=30,
                        help_text="Maximum seconds from navigation request before displaying content, regardless of loading state.",
                        validators=[
                            django.core.validators.MinValueValidator(1)
                        ],
                        verbose_name="preload timeout (seconds)",
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
            ],
            options={
                "verbose_name": "content",
                "verbose_name_plural": "content",
                "ordering": ["-updated_at", "pk"],
            },
        ),
        migrations.CreateModel(
            name="ScreenContent",
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
                    "duration_seconds",
                    models.PositiveIntegerField(
                        default=30,
                        validators=[
                            django.core.validators.MinValueValidator(1)
                        ],
                        verbose_name="time on page (seconds)",
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
            ],
            options={
                "verbose_name": "screen content",
                "verbose_name_plural": "screen content",
                "ordering": ["order", "pk"],
            },
        ),
        migrations.RemoveConstraint(
            model_name="page",
            name="kiosks_page_order_unique",
        ),
        migrations.RemoveConstraint(
            model_name="page",
            name="kiosks_page_url_xor_html",
        ),
        migrations.AddConstraint(
            model_name="content",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("url__gt", ""), ("html_file", "")),
                    models.Q(("url", ""), ("html_file__gt", "")),
                    _connector="OR",
                ),
                name="kiosks_content_url_xor_html",
            ),
        ),
        migrations.AddField(
            model_name="screencontent",
            name="content",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="playlist_entries",
                to="kiosks.content",
                verbose_name="content",
            ),
        ),
        migrations.AddField(
            model_name="screencontent",
            name="screen",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="playlist_entries",
                to="kiosks.screen",
                verbose_name="screen",
            ),
        ),
        migrations.AddField(
            model_name="screen",
            name="contents",
            field=models.ManyToManyField(
                blank=True,
                related_name="screens",
                through="kiosks.ScreenContent",
                to="kiosks.content",
                verbose_name="contents",
            ),
        ),
        migrations.RunPython(copy_pages_to_content, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="screen",
            name="preload_delay_seconds",
        ),
        migrations.RemoveField(
            model_name="screen",
            name="preload_timeout_seconds",
        ),
        migrations.RemoveField(
            model_name="page",
            name="screen",
        ),
        migrations.AddConstraint(
            model_name="screencontent",
            constraint=models.UniqueConstraint(
                fields=("screen", "order"),
                name="kiosks_screen_content_order_unique",
            ),
        ),
        migrations.DeleteModel(
            name="Page",
        ),
    ]
