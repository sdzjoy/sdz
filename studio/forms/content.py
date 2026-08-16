from django import forms

from publishing.models import ContentEntry, Topic


class ContentFilterForm(forms.Form):
    KIND_CHOICES = (("", "全部内容"), *ContentEntry.Kind.choices)
    STATUS_CHOICES = (
        ("", "全部状态"),
        (ContentEntry.Status.DRAFT, "草稿"),
        (ContentEntry.Status.PUBLISHED, "已发布"),
    )
    LOCATION_CHOICES = (("active", "当前内容"), ("trash", "回收站"))

    q = forms.CharField(required=False, max_length=100)
    kind = forms.ChoiceField(required=False, choices=KIND_CHOICES)
    status = forms.ChoiceField(required=False, choices=STATUS_CHOICES)
    topic = forms.ModelChoiceField(required=False, queryset=Topic.objects.none())
    date_from = forms.DateField(required=False, input_formats=("%Y-%m-%d",))
    date_to = forms.DateField(required=False, input_formats=("%Y-%m-%d",))
    location = forms.ChoiceField(
        required=False,
        choices=LOCATION_CHOICES,
        initial="active",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["topic"].queryset = Topic.objects.order_by("name")

    def clean(self):
        cleaned = super().clean()
        date_from = cleaned.get("date_from")
        date_to = cleaned.get("date_to")
        if date_from and date_to and date_from > date_to:
            raise forms.ValidationError("开始日期不能晚于结束日期。")
        return cleaned


class BulkContentActionForm(forms.Form):
    ACTION_CHOICES = (
        ("publish", "发布"),
        ("unpublish", "取消发布"),
        ("trash", "移入回收站"),
    )

    action = forms.ChoiceField(choices=ACTION_CHOICES)
    selected = forms.TypedMultipleChoiceField(coerce=int, choices=())

    def __init__(self, *args, allowed_ids=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["selected"].choices = [(item_id, str(item_id)) for item_id in allowed_ids]


class PermanentDeleteForm(forms.Form):
    reason = forms.CharField(min_length=5, max_length=500, strip=True)
