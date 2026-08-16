from datetime import date

import pytest
from django.db import IntegrityError

from accounts.models import User
from publishing.documents import empty_document
from publishing.models import (
    Article,
    ContentEntry,
    ContentRevision,
    Note,
    Project,
    SiteProfile,
    Tool,
    Topic,
)
from publishing.services import (
    ContentConflict,
    ContentStateError,
    autosave_draft,
    move_to_trash,
    publish_content,
    restore_from_trash,
    restore_revision,
    save_draft,
    unpublish_content,
)

pytestmark = pytest.mark.django_db
TEST_PASSWORD = "a-safe-test-password"  # noqa: S105


def body(value):
    return {
        "schema_version": 1,
        "doc": {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": value}],
                }
            ],
        },
    }


@pytest.fixture
def owner():
    return User.objects.create_user("owner@example.com", TEST_PASSWORD)


@pytest.fixture
def article(owner):
    return Article.objects.create(
        title="液冷系统设计",
        slug="liquid-cooling",
        summary="数据中心液冷系统设计说明",
        author=owner,
        body_json=body("原始正文"),
        published_on=date(2026, 8, 17),
    )


def test_all_content_types_set_kind_and_keep_independent_slugs(owner):
    project = Project.objects.create(title="项目", slug="shared", author=owner)
    article = Article.objects.create(title="文章", slug="shared", author=owner)
    note = Note.objects.create(
        title="随记", slug="note", author=owner, parent_project=project
    )
    tool = Tool.objects.create(
        title="工具", slug="tool", author=owner, parent_project=project
    )

    assert project.kind == ContentEntry.Kind.PROJECT
    assert article.kind == ContentEntry.Kind.ARTICLE
    assert note.kind == ContentEntry.Kind.NOTE
    assert tool.kind == ContentEntry.Kind.TOOL
    assert article.get_absolute_url() == "/articles/shared/"
    assert ContentEntry.objects.get(pk=article.pk).specific == article


def test_slug_is_unique_within_each_content_type(owner, article):
    with pytest.raises(IntegrityError):
        Article.objects.create(title="重复", slug=article.slug, author=owner)


def test_model_derives_safe_html_text_and_reading_time(article):
    assert article.rendered_html == "<p>原始正文</p>"
    assert article.body_text == "原始正文"
    assert article.effective_reading_minutes == 1

    article.reading_minutes = 8
    assert article.effective_reading_minutes == 8


def test_site_profile_renders_about_document():
    profile = SiteProfile.objects.create(about_body_json=body("关于少惰主"))

    assert profile.about_rendered_html == "<p>关于少惰主</p>"
    assert profile.about_body_text == "关于少惰主"
    with pytest.raises(IntegrityError):
        SiteProfile.objects.create()


def test_manual_save_creates_revision_and_updates_topics(owner, article):
    topic = Topic.objects.create(name="数据中心", slug="data-center")

    updated = save_draft(
        article,
        expected_version=0,
        actor=owner,
        title="液冷系统设计（修订）",
        slug=article.slug,
        summary=article.summary,
        body_json=body("新的草稿"),
        featured=True,
        topic_ids=[topic.pk],
        revision_summary="完善初稿",
    )

    revision = updated.revisions.get()
    assert updated.version == 1
    assert updated.body_text == "新的草稿"
    assert updated.featured is True
    assert list(updated.topics.all()) == [topic]
    assert revision.number == 1
    assert revision.action == ContentRevision.Action.SAVE
    assert revision.snapshot["common"]["body_json"] == body("原始正文")


def test_autosave_updates_draft_without_creating_revision(owner, article):
    updated = autosave_draft(
        article,
        expected_version=0,
        title=article.title,
        slug=article.slug,
        summary=article.summary,
        body_json=body("自动保存正文"),
        extra_fields={"reading_minutes": 6},
    )

    assert updated.version == 1
    assert updated.body_text == "自动保存正文"
    assert updated.reading_minutes == 6
    assert updated.revisions.count() == 0


def test_publish_copies_an_immutable_public_snapshot(owner, article):
    topic = Topic.objects.create(name="液冷", slug="liquid-cooling")
    article.topics.add(topic)
    published = publish_content(article, expected_version=0, actor=owner)

    assert published.status == ContentEntry.Status.PUBLISHED
    assert published.published_at is not None
    assert published.published_body_text == "原始正文"
    assert published.published_title == article.title
    assert published.published_slug == article.slug
    assert list(published.published_topics.all()) == [topic]
    assert published.published_metadata["type"]["published_on"] == "2026-08-17"
    assert ContentEntry.objects.published().get(pk=article.pk).pk == article.pk

    changed = save_draft(
        published,
        expected_version=1,
        actor=owner,
        title="液冷系统设计（第二稿）",
        slug="liquid-cooling-v2",
        summary=published.summary,
        body_json=body("尚未发布的新稿"),
        topic_ids=[],
    )

    assert changed.title == "液冷系统设计（第二稿）"
    assert changed.body_text == "尚未发布的新稿"
    assert changed.published_body_text == "原始正文"
    assert changed.published_title == article.title
    assert list(changed.published_topics.all()) == [topic]
    assert changed.get_absolute_url() == "/articles/liquid-cooling/"
    assert changed.status == ContentEntry.Status.PUBLISHED


def test_stale_editor_version_never_overwrites_newer_content(owner, article):
    first = save_draft(
        article,
        expected_version=0,
        actor=owner,
        title=article.title,
        slug=article.slug,
        summary=article.summary,
        body_json=body("窗口一"),
    )

    with pytest.raises(ContentConflict) as caught:
        save_draft(
            article,
            expected_version=0,
            actor=owner,
            title=article.title,
            slug=article.slug,
            summary=article.summary,
            body_json=body("窗口二"),
        )

    assert caught.value.current_version == 1
    assert Article.objects.get(pk=article.pk).body_text == first.body_text == "窗口一"


def test_restoring_revision_changes_draft_but_not_live_snapshot(owner, article):
    published = publish_content(article, expected_version=0, actor=owner)
    changed = save_draft(
        published,
        expected_version=1,
        actor=owner,
        title="新标题",
        slug=article.slug,
        summary=article.summary,
        body_json=body("第二稿"),
    )
    selected = changed.revisions.get(number=2)

    restored = restore_revision(selected, expected_version=2, actor=owner)

    assert restored.title == article.title
    assert restored.body_text == "原始正文"
    assert restored.published_body_text == "原始正文"
    assert restored.status == ContentEntry.Status.PUBLISHED
    assert restored.version == 3
    assert restored.revisions.get(number=3).action == ContentRevision.Action.RESTORE


def test_unpublish_and_trash_control_public_visibility(owner, article):
    published = publish_content(article, expected_version=0, actor=owner)
    unpublished = unpublish_content(published, expected_version=1, actor=owner)

    assert not ContentEntry.objects.published().filter(pk=article.pk).exists()
    assert unpublished.published_body_text == "原始正文"
    with pytest.raises(ContentStateError):
        unpublish_content(unpublished, expected_version=2, actor=owner)

    trashed = move_to_trash(unpublished, expected_version=2, actor=owner)
    assert trashed.is_in_trash
    assert ContentEntry.objects.active().filter(pk=article.pk).count() == 0
    with pytest.raises(ContentStateError):
        publish_content(trashed, expected_version=3, actor=owner)

    recovered = restore_from_trash(trashed, expected_version=3, actor=owner)
    assert not recovered.is_in_trash
    assert recovered.version == 4


def test_revision_retention_keeps_only_latest_thirty(owner, article):
    current = article
    for index in range(35):
        current = save_draft(
            current,
            expected_version=index,
            actor=owner,
            title=current.title,
            slug=current.slug,
            summary=current.summary,
            body_json=body(f"版本 {index}"),
        )

    numbers = list(current.revisions.order_by("number").values_list("number", flat=True))
    assert numbers == list(range(6, 36))
    assert current.revisions.count() == 30


def test_empty_document_default_is_not_shared(owner):
    first = Article.objects.create(title="一", slug="one", author=owner)
    second = Article.objects.create(title="二", slug="two", author=owner)

    assert first.body_json == empty_document()
    assert second.body_json == empty_document()
    assert first.body_json is not second.body_json
