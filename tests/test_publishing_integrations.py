from datetime import date

import pytest
from django.utils import timezone

from accounts.models import User
from notifications.models import Event, ItemSubscription, UserNotification
from notifications.references import resolve_reference
from notifications.services import materialize_event
from publishing.models import Article, Topic
from publishing.services import (
    move_to_trash,
    publish_content,
    restore_from_trash,
    save_draft,
    unpublish_content,
)
from resources.models import Resource, ResourceMirror
from resources.references import resolve_resource_reference
from searchapp.models import SearchDocument
from searchapp.services import rebuild_index, search_documents

pytestmark = pytest.mark.django_db
TEST_PASSWORD = "a-safe-test-password"  # noqa: S105


def user(email="integration-author@example.com", level="L1"):
    return User.objects.create_user(
        email,
        TEST_PASSWORD,
        membership_level=level,
        is_active=True,
    )


def document(text):
    return {
        "schema_version": 1,
        "doc": {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": text}],
                }
            ],
        },
    }


def resource_document(resource_id):
    return {
        "schema_version": 1,
        "doc": {
            "type": "doc",
            "content": [
                {"type": "cloudResource", "attrs": {"resourceId": resource_id}}
            ],
        },
    }


def test_publish_indexes_snapshot_body_and_emits_one_subscriber_event():
    actor = user()
    subscriber = user("content-subscriber@example.com")
    topic = Topic.objects.create(name="冷源系统", slug="cooling-system")
    article = Article.objects.create(
        title="冷冻水系统",
        slug="chilled-water",
        summary="线上摘要",
        body_json=document("一次泵变流量设计正文"),
        published_on=date(2026, 8, 17),
        author=actor,
    )
    article.topics.add(topic)
    ItemSubscription.objects.create(
        user=subscriber,
        item_type="article",
        object_id=article.pk,
    )

    article = publish_content(article, expected_version=0, actor=actor)

    indexed = SearchDocument.objects.get(kind="article", object_id=article.pk)
    assert indexed.title == "冷冻水系统"
    assert indexed.summary == "线上摘要"
    assert "一次泵变流量设计正文" in indexed.search_text
    assert "冷源系统" in indexed.search_text
    assert indexed.url == "/articles/chilled-water/"
    assert indexed.source_updated_at is not None
    assert indexed in search_documents("变流量", None)["article"]

    event = Event.objects.get(event_type=Event.EventType.CONTENT_PUBLISHED)
    assert event.title == "冷冻水系统 已发布"
    assert event.payload["url"] == "/articles/chilled-water/"
    assert materialize_event(event) == 1
    assert UserNotification.objects.filter(user=subscriber, event=event).exists()

    article = save_draft(
        article,
        expected_version=article.version,
        actor=actor,
        title="尚未发布的新标题",
        slug="hidden-draft-slug",
        summary="未发布摘要",
        body_json=document("不能提前进入搜索的新正文"),
    )
    indexed.refresh_from_db()
    assert indexed.title == "冷冻水系统"
    assert "不能提前进入搜索" not in indexed.search_text
    assert Event.objects.filter(event_type=Event.EventType.CONTENT_PUBLISHED).count() == 1

    publish_content(article, expected_version=article.version, actor=actor)
    indexed.refresh_from_db()
    assert indexed.title == "尚未发布的新标题"
    assert indexed.url == "/articles/hidden-draft-slug/"
    assert "不能提前进入搜索的新正文" in indexed.search_text
    assert Event.objects.filter(event_type=Event.EventType.CONTENT_PUBLISHED).count() == 2


def test_unpublish_trash_restore_and_delete_keep_index_in_sync_without_false_event():
    actor = user()
    article = Article.objects.create(
        title="生命周期文章",
        slug="content-lifecycle",
        body_json=document("生命周期正文"),
        author=actor,
    )
    article = publish_content(article, expected_version=0, actor=actor)
    assert SearchDocument.objects.filter(kind="article", object_id=article.pk).exists()
    publication_count = Event.objects.filter(
        event_type=Event.EventType.CONTENT_PUBLISHED
    ).count()

    article = unpublish_content(article, expected_version=article.version, actor=actor)
    assert not SearchDocument.objects.filter(kind="article", object_id=article.pk).exists()

    article = publish_content(article, expected_version=article.version, actor=actor)
    assert SearchDocument.objects.filter(kind="article", object_id=article.pk).exists()
    publication_count += 1
    article = move_to_trash(article, expected_version=article.version, actor=actor)
    assert not SearchDocument.objects.filter(kind="article", object_id=article.pk).exists()

    article = restore_from_trash(article, expected_version=article.version, actor=actor)
    assert SearchDocument.objects.filter(kind="article", object_id=article.pk).exists()
    assert (
        Event.objects.filter(event_type=Event.EventType.CONTENT_PUBLISHED).count()
        == publication_count
    )

    object_id = article.pk
    article.delete()
    assert not SearchDocument.objects.filter(kind="article", object_id=object_id).exists()


def test_rebuild_removes_stale_documents_and_uses_only_public_snapshot():
    actor = user()
    published = publish_content(
        Article.objects.create(
            title="重建索引文章",
            slug="rebuild-index",
            body_json=document("重建索引正文"),
            author=actor,
        ),
        expected_version=0,
        actor=actor,
    )
    Article.objects.create(title="重建时排除草稿", slug="rebuild-draft", author=actor)
    SearchDocument.objects.create(
        kind="article",
        object_id="999999",
        title="过期索引",
        url="/articles/stale/",
    )

    count = rebuild_index()

    assert count >= 1
    indexed = SearchDocument.objects.get(kind="article", object_id=published.pk)
    assert indexed.title == published.published_title
    assert "重建索引正文" in indexed.search_text
    assert not SearchDocument.objects.filter(object_id="999999").exists()
    assert not SearchDocument.objects.filter(title="重建时排除草稿").exists()


def test_saved_content_reference_uses_snapshot_and_disappears_after_unpublish():
    actor = user()
    article = publish_content(
        Article.objects.create(
            title="收藏中的线上标题",
            slug="saved-public-title",
            body_json=document("正文"),
            author=actor,
        ),
        expected_version=0,
        actor=actor,
    )
    article = save_draft(
        article,
        expected_version=article.version,
        actor=actor,
        title="收藏中不能出现的草稿标题",
        slug="saved-hidden-draft",
        summary="",
        body_json=document("新正文"),
    )

    resolved = resolve_reference("article", article.pk, actor)
    assert resolved["title"] == "收藏中的线上标题"
    assert resolved["url"] == "/articles/saved-public-title/"

    article = unpublish_content(article, expected_version=article.version, actor=actor)
    assert resolve_reference("article", article.pk, actor) is None


def test_resource_embed_interface_enforces_membership_and_active_mirrors(client):
    actor = user()
    lower_member = user("lower-resource@example.com", "L1")
    allowed_member = user("allowed-resource@example.com", "L2")
    resource = Resource.objects.create(
        title="高级液冷资料",
        slug="advanced-liquid-cooling",
        summary="高级资料",
        access_level=Resource.AccessLevel.ADVANCED,
        status=Resource.Status.PUBLISHED,
        published_at=timezone.now(),
    )
    active = ResourceMirror.objects.create(
        resource=resource,
        provider=ResourceMirror.Provider.BAIDU,
        share_url="https://pan.example.test/s/allowed-resource",
        extraction_code="SAFE9",
    )
    ResourceMirror.objects.create(
        resource=resource,
        provider=ResourceMirror.Provider.PCLOUD,
        share_url="https://drive.example.test/s/failed-resource",
        extraction_code="FAIL9",
        status=ResourceMirror.Status.FAILED,
    )

    assert resolve_resource_reference(resource.pk, lower_member) is None
    resolved = resolve_resource_reference(resource.pk, allowed_member)
    assert resolved.title == resource.title
    assert list(resolved.active_mirrors) == [active]

    article = publish_content(
        Article.objects.create(
            title="含会员资源的文章",
            slug="resource-embedded-article",
            body_json=resource_document(resource.pk),
            author=actor,
        ),
        expected_version=0,
        actor=actor,
    )

    anonymous = client.get(article.get_absolute_url())
    anonymous_body = anonymous.content.decode()
    assert resource.title not in anonymous_body
    assert active.share_url not in anonymous_body
    assert active.extraction_code not in anonymous_body

    client.force_login(allowed_member)
    allowed_body = client.get(article.get_absolute_url()).content.decode()
    assert resource.title in allowed_body
    assert active.share_url in allowed_body
    assert active.extraction_code in allowed_body

    User.objects.filter(pk=allowed_member.pk).update(membership_level="L1")
    revoked_body = client.get(article.get_absolute_url()).content.decode()
    assert resource.title not in revoked_body
    assert active.share_url not in revoked_body
    assert active.extraction_code not in revoked_body
