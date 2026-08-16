from django import forms

from publishing.documents import DocumentValidationError, extract_text, validate_document
from publishing.models import Project, Topic


class ArticlePayloadForm(forms.Form):
    title = forms.CharField(required=False, max_length=200, strip=True)
    slug = forms.SlugField(required=False, max_length=160, allow_unicode=True)
    summary = forms.CharField(required=False, max_length=500, strip=True)
    body_json = forms.JSONField()
    version = forms.IntegerField(min_value=0)
    featured = forms.BooleanField(required=False)
    published_on = forms.DateField(input_formats=("%Y-%m-%d",))
    reading_minutes = forms.IntegerField(required=False, min_value=1, max_value=1440)
    parent_project = forms.ModelChoiceField(required=False, queryset=Project.objects.none())
    topics = forms.ModelMultipleChoiceField(required=False, queryset=Topic.objects.none())

    def __init__(self, *args, intent="autosave", **kwargs):
        super().__init__(*args, **kwargs)
        self.intent = intent
        self.fields["parent_project"].queryset = Project.objects.active()
        self.fields["topics"].queryset = Topic.objects.order_by("name")
        self.document_warnings = ()

    def clean_title(self):
        title = self.cleaned_data["title"]
        if self.intent in {"save", "publish"} and not title:
            raise forms.ValidationError("手工保存或发布前请填写标题。")
        return title

    def clean_body_json(self):
        value = self.cleaned_data["body_json"]
        try:
            validated = validate_document(value)
        except DocumentValidationError as error:
            raise forms.ValidationError(str(error)) from error
        self.document_warnings = validated.warnings
        return validated.as_dict()

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("summary") and cleaned.get("body_json"):
            cleaned["summary"] = extract_text(cleaned["body_json"])[:160]
        return cleaned
