from datetime import date
from typing import Any

from django.db import models

from publishing.models import ContentEntry, ContentRevision

SNAPSHOT_SCHEMA_VERSION = 1
MAX_REVISIONS_PER_CONTENT = 30
COMMON_SNAPSHOT_FIELDS = (
    "title",
    "slug",
    "summary",
    "featured",
    "cover_asset_id",
    "body_json",
)
TYPE_SNAPSHOT_FIELDS = {
    ContentEntry.Kind.ARTICLE: ("published_on", "reading_minutes", "parent_project_id"),
    ContentEntry.Kind.PROJECT: ("project_status", "started_on", "completed_on"),
    ContentEntry.Kind.NOTE: ("noted_on", "parent_project_id", "promoted_article_id"),
    ContentEntry.Kind.TOOL: (
        "launched_on",
        "tool_status",
        "service_url",
        "source_url",
        "parent_project_id",
    ),
}


def _json_value(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    return value


def _typed(content: ContentEntry) -> ContentEntry:
    if type(content) is not ContentEntry:
        return content
    return content.specific


def snapshot_content(content: ContentEntry) -> dict[str, Any]:
    typed = _typed(content)
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "kind": content.kind,
        "common": {
            field: _json_value(getattr(content, field)) for field in COMMON_SNAPSHOT_FIELDS
        },
        "topics": list(content.topics.order_by("pk").values_list("pk", flat=True)),
        "type": {
            field: _json_value(getattr(typed, field))
            for field in TYPE_SNAPSHOT_FIELDS.get(content.kind, ())
        },
    }


def create_revision(
    content: ContentEntry,
    *,
    action: str,
    actor,
    summary: str = "",
) -> ContentRevision:
    revision = ContentRevision.objects.create(
        content=content,
        number=content.version + 1,
        action=action,
        snapshot=snapshot_content(content),
        summary=summary,
        created_by=actor,
    )
    stale_ids = list(
        ContentRevision.objects.filter(content=content)
        .order_by("-number", "-pk")
        .values_list("pk", flat=True)[MAX_REVISIONS_PER_CONTENT:]
    )
    if stale_ids:
        ContentRevision.objects.filter(pk__in=stale_ids).delete()
    return revision


def apply_snapshot(content: ContentEntry, snapshot: dict[str, Any]) -> set[str]:
    if snapshot.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("不支持的版本快照格式")
    if snapshot.get("kind") != content.kind:
        raise ValueError("版本快照与内容类型不匹配")

    common = snapshot.get("common")
    type_data = snapshot.get("type")
    topics = snapshot.get("topics")
    if (
        not isinstance(common, dict)
        or not isinstance(type_data, dict)
        or not isinstance(topics, list)
    ):
        raise ValueError("版本快照结构不完整")

    updated_fields = set()
    for field in COMMON_SNAPSHOT_FIELDS:
        if field not in common:
            raise ValueError(f"版本快照缺少字段：{field}")
        setattr(content, field, common[field])
        updated_fields.add(field)

    typed = _typed(content)
    for field in TYPE_SNAPSHOT_FIELDS.get(content.kind, ()):
        if field not in type_data:
            raise ValueError(f"版本快照缺少字段：{field}")
        model_field = typed._meta.get_field(field.removesuffix("_id"))
        value = type_data[field]
        if isinstance(model_field, models.DateField) and value is not None:
            value = date.fromisoformat(value)
        setattr(typed, field, value)
        updated_fields.add(field)

    content._snapshot_topic_ids = topics
    return updated_fields
