from django import forms
from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.utils.translation import gettext_lazy as _

from recurrence.forms import (
    RecurrenceWidget,
    find_recurrence_i18n_js_catalog,
)

from .models import (
    MAX_HTML_LENGTH,
    Content,
    Screen,
    validate_media_upload,
)


class ContentAdminForm(forms.ModelForm):
    html_upload = forms.FileField(
        label=_("HTML file"),
        required=False,
        widget=forms.ClearableFileInput,
        help_text=_("Upload a UTF-8 self-contained HTML document."),
    )

    class Meta:
        model = Content
        fields = [
            "label",
            "url",
            "html_upload",
            "media",
            "preload_delay_seconds",
            "preload_timeout_seconds",
            "injected_css",
            "injected_javascript_before",
            "injected_javascript_after",
        ]
        widgets = {
            "media": forms.ClearableFileInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["preload_delay_seconds"].required = False
        self.fields["preload_timeout_seconds"].required = False

    def clean_html_upload(self):
        uploaded = self.cleaned_data.get("html_upload")
        if uploaded is None:
            return None
        if uploaded.size > MAX_HTML_LENGTH:
            raise ValidationError(_("HTML document is too large."))
        try:
            return uploaded.read().decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationError(_("HTML document must be UTF-8.")) from exc

    def clean(self):
        cleaned = super().clean()
        url = cleaned.get("url")
        html = cleaned.get("html_upload")
        media = cleaned.get("media")
        has_media_upload = isinstance(media, UploadedFile)
        provided = sum((bool(url), bool(html), has_media_upload))
        if provided > 1:
            raise ValidationError(
                _("Choose exactly one URL, HTML file, or media file.")
            )
        if has_media_upload:
            _kind, detected_mime = validate_media_upload(media)
            media.content_type = detected_mime
        if html:
            self.instance.html = html
            self.instance.url = ""
            self.instance.media = ""
        elif has_media_upload:
            self.instance.html = ""
            self.instance.url = ""
        elif url:
            self.instance.html = ""
            self.instance.media = ""
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        html = self.cleaned_data.get("html_upload")
        if html:
            instance.html = html
            instance.url = ""
            instance.media = ""
        elif self.cleaned_data.get("media") not in (None, False, ""):
            instance.html = ""
            instance.url = ""
        elif self.cleaned_data.get("url"):
            instance.html = ""
            instance.media = ""
        if commit:
            instance.save()
        return instance


class ScheduleRecurrenceWidget(RecurrenceWidget):
    def get_media(self):
        extra = "" if settings.DEBUG else ".min"
        js = [
            f"admin/js/vendor/jquery/jquery{extra}.js",
            "admin/js/jquery.init.js",
            staticfiles_storage.url("recurrence/js/recurrence.js"),
            staticfiles_storage.url("recurrence/js/recurrence-widget.js"),
            staticfiles_storage.url("recurrence/js/recurrence-widget.init.js"),
        ]
        i18n_media = find_recurrence_i18n_js_catalog()
        if i18n_media:
            js.insert(0, i18n_media)
        js.append(staticfiles_storage.url("kiosks/recurrence-time.js"))
        return forms.Media(
            js=js,
            css={
                "all": (
                    staticfiles_storage.url("recurrence/css/recurrence.css"),
                )
            },
        )

    media = property(get_media)


class ScreenAdminForm(forms.ModelForm):
    class Meta:
        model = Screen
        fields = [
            "name",
            "enabled",
            "on_schedule",
            "off_schedule",
            "reported_power_state",
        ]
        widgets = {
            "on_schedule": ScheduleRecurrenceWidget,
            "off_schedule": ScheduleRecurrenceWidget,
        }
