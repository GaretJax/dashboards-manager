from django import forms
from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage

from recurrence.forms import (
    RecurrenceWidget,
    find_recurrence_i18n_js_catalog,
)

from .models import Screen


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
