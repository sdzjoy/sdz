from django import forms

from accounts.models import User
from publishing.models import SiteProfile
from studio.permissions import ROLE_LABELS, StudioRole, get_studio_role


class UserManagementForm(forms.Form):
    membership_level = forms.ChoiceField(
        label="会员等级",
        choices=User.MembershipLevel.choices,
    )
    studio_role = forms.ChoiceField(
        label="后台角色",
        required=False,
        choices=[("", "无后台权限")]
        + [(role.value, ROLE_LABELS[role]) for role in StudioRole],
    )
    is_active = forms.BooleanField(label="账号可用", required=False)
    reason = forms.CharField(
        label="变更原因",
        max_length=240,
        help_text="用于会员变更历史和后台审计，不会公开显示。",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, target_user, actor, **kwargs):
        self.target_user = target_user
        self.actor = actor
        role = get_studio_role(target_user)
        kwargs.setdefault(
            "initial",
            {
                "membership_level": target_user.membership_level,
                "studio_role": role.value if role else "",
                "is_active": target_user.is_active,
            },
        )
        super().__init__(*args, **kwargs)
        if target_user.is_superuser:
            self.fields["studio_role"].disabled = True
            self.fields["studio_role"].initial = StudioRole.OWNER

    def clean(self):
        cleaned = super().clean()
        if not cleaned:
            return cleaned
        if self.target_user.pk == self.actor.pk:
            if not cleaned.get("is_active"):
                self.add_error("is_active", "不能停用当前登录账号。")
            if cleaned.get("membership_level") != self.target_user.membership_level:
                self.add_error("membership_level", "不能在这里修改自己的会员等级。")
        if self.target_user.is_superuser:
            if cleaned.get("membership_level") != User.MembershipLevel.OWNER:
                self.add_error("membership_level", "超级用户必须保持站长等级。")
            if cleaned.get("studio_role") != StudioRole.OWNER:
                self.add_error("studio_role", "超级用户必须保持站长后台角色。")
        return cleaned


class SiteProfileForm(forms.ModelForm):
    class Meta:
        model = SiteProfile
        fields = (
            "site_name",
            "tagline",
            "owner_name",
            "article_intro",
            "project_intro",
            "note_intro",
            "tool_intro",
            "about_intro",
        )
        widgets = {
            "tagline": forms.Textarea(attrs={"rows": 2}),
            "article_intro": forms.Textarea(attrs={"rows": 2}),
            "project_intro": forms.Textarea(attrs={"rows": 2}),
            "note_intro": forms.Textarea(attrs={"rows": 2}),
            "tool_intro": forms.Textarea(attrs={"rows": 2}),
            "about_intro": forms.Textarea(attrs={"rows": 3}),
        }
