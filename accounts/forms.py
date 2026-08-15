from django import forms

from .security import verify_turnstile


class SignupExtraForm(forms.Form):
    display_name = forms.CharField(
        label="昵称",
        max_length=80,
        required=True,
        widget=forms.TextInput(attrs={"autocomplete": "nickname"}),
    )
    turnstile_token = forms.CharField(
        required=False,
        widget=forms.HiddenInput,
    )

    def clean_turnstile_token(self):
        token = self.cleaned_data.get("turnstile_token", "")
        if not verify_turnstile(token):
            raise forms.ValidationError("人机验证未通过，请刷新页面后重试。")
        return token

    def signup(self, request, user):
        user.display_name = self.cleaned_data["display_name"].strip()
        user.save(update_fields=("display_name",))
