from django import forms

from .models import NotificationPreference


class NotificationPreferenceForm(forms.ModelForm):
    class Meta:
        model = NotificationPreference
        fields = (
            "email_enabled",
            "immediate_standard",
            "immediate_resource",
            "membership",
            "weekly_digest",
        )

