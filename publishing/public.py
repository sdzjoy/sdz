import math
import re
from datetime import date
from functools import cached_property

from publishing.documents import render_document, validate_document
from publishing.models import ContentEntry, Project, Tool

CJK_CHARACTER_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
LATIN_WORD_RE = re.compile(r"\b[A-Za-z0-9][A-Za-z0-9'-]*\b")


def _date_value(value):
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


class PublishedContent:
    """Read-only view of a ContentEntry's frozen public snapshot.

    Draft fields are deliberately not proxied through ``__getattr__`` so a template
    cannot accidentally expose unpublished edits.
    """

    def __init__(self, entry: ContentEntry, *, user=None):
        self._entry = entry
        self._user = user

    @property
    def pk(self):
        return self._entry.pk

    @property
    def kind(self):
        return self._entry.kind

    @property
    def title(self):
        return self._entry.published_title

    @property
    def slug(self):
        return self._entry.published_slug

    @property
    def summary(self):
        return self._entry.published_summary

    @property
    def featured(self):
        return self._entry.published_featured

    @property
    def published_at(self):
        return self._entry.published_at

    @property
    def updated_at(self):
        return self._entry.updated_at

    @property
    def topics(self):
        return self._entry.published_topics

    @property
    def cover_asset(self):
        return self._entry.published_cover_asset

    @property
    def url(self):
        return self._entry.get_absolute_url()

    def get_absolute_url(self):
        return self.url

    @property
    def metadata(self):
        value = self._entry.published_metadata
        return value if isinstance(value, dict) else {}

    @property
    def type_metadata(self):
        value = self.metadata.get("type", {})
        return value if isinstance(value, dict) else {}

    @cached_property
    def body_html(self):
        document = validate_document(self._entry.published_body_json)
        return render_document(document, user=self._user)

    @property
    def status(self):
        if self.kind == ContentEntry.Kind.PROJECT:
            return self.type_metadata.get("project_status", "")
        if self.kind == ContentEntry.Kind.TOOL:
            return self.type_metadata.get("tool_status", "")
        return ""

    def get_status_display(self):
        choices = {
            ContentEntry.Kind.PROJECT: dict(Project.ProjectStatus.choices),
            ContentEntry.Kind.TOOL: dict(Tool.ToolStatus.choices),
        }
        return choices.get(self.kind, {}).get(self.status, self.status)

    @property
    def published_on(self):
        return _date_value(self.type_metadata.get("published_on"))

    @property
    def noted_on(self):
        return _date_value(self.type_metadata.get("noted_on"))

    @property
    def launched_on(self):
        return _date_value(self.type_metadata.get("launched_on"))

    @property
    def started_on(self):
        return _date_value(self.type_metadata.get("started_on"))

    @property
    def completed_on(self):
        return _date_value(self.type_metadata.get("completed_on"))

    @property
    def timeline_date(self):
        return self.published_on or self.noted_on or self.launched_on or self.started_on

    @property
    def reading_minutes(self):
        return self.type_metadata.get("reading_minutes")

    @property
    def effective_reading_minutes(self):
        if self.reading_minutes:
            return self.reading_minutes
        text = self._entry.published_body_text
        chinese_characters = len(CJK_CHARACTER_RE.findall(text))
        latin_words = len(LATIN_WORD_RE.findall(text))
        return max(1, math.ceil(chinese_characters / 350 + latin_words / 180))

    @property
    def service_url(self):
        return self.type_metadata.get("service_url", "")

    @property
    def source_url(self):
        return self.type_metadata.get("source_url", "")

    def _related_content(self, field):
        object_id = self.type_metadata.get(field)
        if not object_id:
            return None
        related = (
            ContentEntry.objects.published()
            .select_related("published_cover_asset")
            .prefetch_related("published_topics")
            .filter(pk=object_id)
            .first()
        )
        return PublishedContent(related, user=self._user) if related else None

    @cached_property
    def project(self):
        return self._related_content("parent_project_id")

    @cached_property
    def promoted_article(self):
        return self._related_content("promoted_article_id")

    @cached_property
    def timeline(self):
        if self.kind != ContentEntry.Kind.PROJECT:
            return []
        related = (
            ContentEntry.objects.published()
            .filter(
                kind__in=(
                    ContentEntry.Kind.ARTICLE,
                    ContentEntry.Kind.NOTE,
                    ContentEntry.Kind.TOOL,
                ),
                published_metadata__type__parent_project_id=self.pk,
            )
            .select_related("published_cover_asset")
            .prefetch_related("published_topics")
        )
        items = []
        for entry in related:
            page = PublishedContent(entry, user=self._user)
            items.append({"kind": entry.kind, "date": page.timeline_date, "page": page})
        return sorted(
            items,
            key=lambda item: (item["date"] or date.min, item["page"].pk),
            reverse=True,
        )

    @property
    def reference_entries(self):
        return []


def as_published(entries, *, user=None):
    return [PublishedContent(entry, user=user) for entry in entries]
