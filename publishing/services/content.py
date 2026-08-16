from django.db import transaction
from django.utils import timezone

from publishing.documents import validate_document
from publishing.models import ContentEntry, ContentRevision

from .revisions import apply_snapshot, create_revision, snapshot_content

_UNSET = object()
TYPE_DRAFT_FIELDS = {
    ContentEntry.Kind.ARTICLE: {"published_on", "reading_minutes", "parent_project_id"},
    ContentEntry.Kind.PROJECT: {"project_status", "started_on", "completed_on"},
    ContentEntry.Kind.NOTE: {"noted_on", "parent_project_id", "promoted_article_id"},
    ContentEntry.Kind.TOOL: {
        "launched_on",
        "tool_status",
        "service_url",
        "source_url",
        "parent_project_id",
    },
}


class ContentConflict(RuntimeError):
    def __init__(self, current_version: int):
        super().__init__("内容已在其他窗口中更新")
        self.current_version = current_version


class ContentStateError(RuntimeError):
    pass


def _locked_typed_content(content) -> ContentEntry:
    locked = ContentEntry.objects.select_for_update().get(pk=content.pk)
    return locked.specific


def _check_editable(content: ContentEntry, expected_version: int) -> None:
    if content.version != expected_version:
        raise ContentConflict(content.version)
    if content.deleted_at is not None:
        raise ContentStateError("回收站中的内容不能编辑或发布")


def _reload(content: ContentEntry):
    return type(content).objects.get(pk=content.pk)


def _apply_draft_changes(
    locked,
    *,
    title: str,
    slug: str,
    summary: str,
    validated_body,
    featured: bool | None = None,
    cover_asset=_UNSET,
    topic_ids=None,
    extra_fields=None,
):
    locked.title = title
    locked.slug = slug
    locked.summary = summary
    locked.body_json = validated_body.as_dict()
    if featured is not None:
        locked.featured = featured
    if cover_asset is not _UNSET:
        locked.cover_asset = cover_asset
    extra_fields = extra_fields or {}
    unexpected = set(extra_fields) - TYPE_DRAFT_FIELDS.get(locked.kind, set())
    if unexpected:
        raise ValueError(f"内容类型不支持字段：{', '.join(sorted(unexpected))}")
    for field, value in extra_fields.items():
        setattr(locked, field, value)
    locked.version += 1
    updated_fields = {"title", "slug", "summary", "body_json", "version", "updated_at"}
    if featured is not None:
        updated_fields.add("featured")
    if cover_asset is not _UNSET:
        updated_fields.add("cover_asset")
    updated_fields.update(extra_fields)
    locked.save(update_fields=updated_fields)
    if topic_ids is not None:
        locked.topics.set(topic_ids)
    return _reload(locked)


@transaction.atomic
def autosave_draft(
    content,
    *,
    expected_version: int,
    title: str,
    slug: str,
    summary: str,
    body_json,
    featured: bool | None = None,
    cover_asset=_UNSET,
    topic_ids=None,
    extra_fields=None,
):
    locked = _locked_typed_content(content)
    _check_editable(locked, expected_version)
    validated = validate_document(body_json)
    return _apply_draft_changes(
        locked,
        title=title,
        slug=slug,
        summary=summary,
        validated_body=validated,
        featured=featured,
        cover_asset=cover_asset,
        topic_ids=topic_ids,
        extra_fields=extra_fields,
    )


@transaction.atomic
def save_draft(
    content,
    *,
    expected_version: int,
    actor,
    title: str,
    slug: str,
    summary: str,
    body_json,
    featured: bool | None = None,
    cover_asset=_UNSET,
    topic_ids=None,
    extra_fields=None,
    revision_summary: str = "",
):
    locked = _locked_typed_content(content)
    _check_editable(locked, expected_version)
    validated = validate_document(body_json)
    create_revision(
        locked,
        action=ContentRevision.Action.SAVE,
        actor=actor,
        summary=revision_summary,
    )
    return _apply_draft_changes(
        locked,
        title=title,
        slug=slug,
        summary=summary,
        validated_body=validated,
        featured=featured,
        cover_asset=cover_asset,
        topic_ids=topic_ids,
        extra_fields=extra_fields,
    )


@transaction.atomic
def publish_content(content, *, expected_version: int, actor, revision_summary: str = ""):
    locked = _locked_typed_content(content)
    _check_editable(locked, expected_version)
    create_revision(
        locked,
        action=ContentRevision.Action.PUBLISH,
        actor=actor,
        summary=revision_summary,
    )
    snapshot = snapshot_content(locked)
    locked.published_body_json = locked.body_json
    locked.published_title = locked.title
    locked.published_slug = locked.slug
    locked.published_summary = locked.summary
    locked.published_featured = locked.featured
    locked.published_cover_asset = locked.cover_asset
    locked.published_metadata = {
        "schema_version": snapshot["schema_version"],
        "kind": snapshot["kind"],
        "type": snapshot["type"],
    }
    locked.status = ContentEntry.Status.PUBLISHED
    if locked.published_at is None:
        locked.published_at = timezone.now()
    locked.version += 1
    locked.save(
        update_fields={
            "published_body_json",
            "published_title",
            "published_slug",
            "published_summary",
            "published_featured",
            "published_cover_asset",
            "published_metadata",
            "status",
            "published_at",
            "version",
            "updated_at",
        }
    )
    locked.published_topics.set(snapshot["topics"])
    return _reload(locked)


@transaction.atomic
def unpublish_content(content, *, expected_version: int, actor, revision_summary: str = ""):
    locked = _locked_typed_content(content)
    _check_editable(locked, expected_version)
    if locked.status != ContentEntry.Status.PUBLISHED:
        raise ContentStateError("内容尚未发布")
    create_revision(
        locked,
        action=ContentRevision.Action.UNPUBLISH,
        actor=actor,
        summary=revision_summary,
    )
    locked.status = ContentEntry.Status.DRAFT
    locked.version += 1
    locked.save(update_fields={"status", "version", "updated_at"})
    return _reload(locked)


@transaction.atomic
def restore_revision(revision, *, expected_version: int, actor, revision_summary: str = ""):
    locked = _locked_typed_content(revision.content)
    _check_editable(locked, expected_version)
    selected = ContentRevision.objects.get(pk=revision.pk, content_id=locked.pk)
    create_revision(
        locked,
        action=ContentRevision.Action.RESTORE,
        actor=actor,
        summary=revision_summary,
    )
    updated_fields = apply_snapshot(locked, selected.snapshot)
    locked.version += 1
    updated_fields |= {"version", "updated_at"}
    locked.save(update_fields=updated_fields)
    locked.topics.set(locked._snapshot_topic_ids)
    return _reload(locked)


@transaction.atomic
def move_to_trash(content, *, expected_version: int, actor, revision_summary: str = ""):
    locked = _locked_typed_content(content)
    _check_editable(locked, expected_version)
    create_revision(
        locked,
        action=ContentRevision.Action.DELETE,
        actor=actor,
        summary=revision_summary,
    )
    locked.deleted_at = timezone.now()
    locked.deleted_by = actor
    locked.version += 1
    locked.save(update_fields={"deleted_at", "deleted_by", "version", "updated_at"})
    return _reload(locked)


@transaction.atomic
def restore_from_trash(content, *, expected_version: int, actor, revision_summary: str = ""):
    locked = _locked_typed_content(content)
    if locked.version != expected_version:
        raise ContentConflict(locked.version)
    if locked.deleted_at is None:
        raise ContentStateError("内容不在回收站中")
    create_revision(
        locked,
        action=ContentRevision.Action.TRASH_RESTORE,
        actor=actor,
        summary=revision_summary,
    )
    locked.deleted_at = None
    locked.deleted_by = None
    locked.version += 1
    locked.save(update_fields={"deleted_at", "deleted_by", "version", "updated_at"})
    return _reload(locked)
