from django.core.validators import (
    FileExtensionValidator,
    MaxLengthValidator,
)
from django.db import migrations, models

MAX_HTML_LENGTH = 1024 * 1024
MEDIA_EXTENSIONS = [
    "jpg",
    "jpeg",
    "png",
    "gif",
    "webp",
    "avif",
    "svg",
    "mp4",
    "webm",
]


def copy_html_files_to_database(apps, schema_editor):
    del schema_editor
    content_model = apps.get_model("kiosks", "Content")
    for content in content_model.objects.exclude(html_file="").iterator():
        try:
            with content.html_file.open("rb") as stream:
                value = stream.read(MAX_HTML_LENGTH + 1).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RuntimeError(
                f"HTML content {content.pk} is not valid UTF-8"
            ) from exc
        if len(value) > MAX_HTML_LENGTH:
            raise RuntimeError(
                f"HTML content {content.pk} exceeds {MAX_HTML_LENGTH} bytes"
            )
        content.html = value
        content.save(update_fields=["html"])


class Migration(migrations.Migration):
    dependencies = [
        ("kiosks", "0010_content_label"),
    ]

    operations = [
        migrations.AddField(
            model_name="content",
            name="html",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Full self-contained HTML document.",
                max_length=MAX_HTML_LENGTH,
                validators=[MaxLengthValidator(MAX_HTML_LENGTH)],
                verbose_name="HTML",
            ),
        ),
        migrations.AddField(
            model_name="content",
            name="media",
            field=models.FileField(
                blank=True,
                default="",
                help_text="Upload a Chrome-compatible image or video.",
                upload_to="contents/",
                validators=[FileExtensionValidator(MEDIA_EXTENSIONS)],
                verbose_name="media file",
            ),
        ),
        migrations.RunPython(
            copy_html_files_to_database,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RemoveConstraint(
            model_name="content",
            name="kiosks_content_url_xor_html",
        ),
        migrations.RemoveField(
            model_name="content",
            name="html_file",
        ),
        migrations.AddConstraint(
            model_name="content",
            constraint=models.CheckConstraint(
                condition=(
                    (
                        ~models.Q(url="")
                        & models.Q(html="")
                        & models.Q(media="")
                    )
                    | (
                        models.Q(url="")
                        & ~models.Q(html="")
                        & models.Q(media="")
                    )
                    | (
                        models.Q(url="")
                        & models.Q(html="")
                        & ~models.Q(media="")
                    )
                ),
                name="kiosks_content_single_source",
            ),
        ),
    ]
