import json
from datetime import date
from unittest.mock import patch

import pytest
from allauth.mfa.models import Authenticator
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse

from accounts.models import User
from notifications.models import Event
from publishing.models import Article, ContentRevision, Project, Topic
from searchapp.models import SearchDocument
from studio.models import AuditEvent
from studio.permissions import ROLE_GROUPS, StudioRole

pytestmark = pytest.mark.django_db
TEST_PASSWORD = "a-safe-test-password"  # noqa: S105


def backend_user(role=StudioRole.EDITOR, email="article-editor@example.com"):
    user = User.objects.create_user(email, TEST_PASSWORD)
    user.groups.add(Group.objects.get(name=ROLE_GROUPS[role]))
    Authenticator.objects.create(
        user=user,
        type=Authenticator.Type.TOTP,
        data={"secret": "encrypted-test-placeholder"},
    )
    return user


def document(text="数据中心冷源设计"):
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


def article_payload(*, version=0, title="数据中心暖通设计", text="数据中心冷源设计"):
    return {
        "title": title,
        "slug": "",
        "summary": "",
        "body_json": document(text),
        "version": version,
        "featured": False,
        "published_on": "2026-08-17",
        "reading_minutes": None,
        "parent_project": None,
        "topics": [],
    }


def post_json(client, url, payload):
    return client.post(url, json.dumps(payload), content_type="application/json")


def test_editor_can_open_article_pages_but_resource_admin_cannot(client):
    editor = backend_user()
    article = Article.objects.create(title="编辑中的文章", slug="editing", author=editor)
    client.force_login(editor)

    create_response = client.get(reverse("studio:article_create"))
    edit_response = client.get(reverse("studio:article_edit", args=(article.pk,)))

    assert create_response.status_code == 200
    assert edit_response.status_code == 200
    assert "像写公众号一样，专心写正文" in create_response.content.decode()
    assert "编辑中的文章" in edit_response.content.decode()
    assert create_response["Cache-Control"] == "private, no-store"

    resource_admin = backend_user(
        StudioRole.RESOURCE_ADMIN,
        email="article-resource@example.com",
    )
    client.force_login(resource_admin)
    assert client.get(reverse("studio:article_create")).status_code == 403


def test_first_autosave_creates_draft_with_derived_summary_and_slug(client):
    editor = backend_user()
    client.force_login(editor)
    payload = article_payload(text="冷冻水系统的自动保存正文") | {"intent": "autosave"}

    response = post_json(client, reverse("studio:api_article_create"), payload)
    body = response.json()
    article = Article.objects.get()

    assert response.status_code == 201
    assert body["article"]["id"] == article.pk
    assert body["article"]["version"] == 0
    assert article.slug == "数据中心暖通设计"
    assert article.summary == "冷冻水系统的自动保存正文"
    assert article.revisions.count() == 0
    assert body["article"]["autosave_url"].endswith(f"/{article.pk}/autosave/")


def test_existing_autosave_updates_settings_without_revision(client):
    editor = backend_user()
    project = Project.objects.create(title="液冷项目", slug="liquid-project", author=editor)
    topic = Topic.objects.create(name="液冷", slug="liquid-cooling")
    article = Article.objects.create(title="旧标题", slug="old-title", author=editor)
    client.force_login(editor)
    payload = article_payload(version=0, title="新标题", text="新的正文") | {
        "slug": "new-title",
        "featured": True,
        "published_on": "2026-09-01",
        "reading_minutes": 8,
        "parent_project": project.pk,
        "topics": [topic.pk],
    }

    response = post_json(
        client,
        reverse("studio:api_article_autosave", args=(article.pk,)),
        payload,
    )
    article.refresh_from_db()

    assert response.status_code == 200
    assert article.version == 1
    assert article.title == "新标题"
    assert article.body_text == "新的正文"
    assert article.featured is True
    assert article.published_on == date(2026, 9, 1)
    assert article.reading_minutes == 8
    assert article.parent_project == project
    assert list(article.topics.all()) == [topic]
    assert article.revisions.count() == 0


def test_manual_save_creates_revision_and_audit_event(client):
    editor = backend_user()
    article = Article.objects.create(title="原稿", slug="manual-save", author=editor)
    client.force_login(editor)
    payload = article_payload(version=0, title="手工保存后的文章")

    response = post_json(
        client,
        reverse("studio:api_article_save", args=(article.pk,)),
        payload,
    )
    article.refresh_from_db()

    assert response.status_code == 200
    assert article.version == 1
    assert article.revisions.get().action == ContentRevision.Action.SAVE
    audit = AuditEvent.objects.get(action=AuditEvent.Action.MANUAL_SAVE)
    assert audit.actor == editor
    assert audit.object_id == str(article.pk)


def test_stale_version_returns_conflict_without_overwriting_article(client):
    editor = backend_user()
    article = Article.objects.create(title="服务器上的版本", slug="conflict", author=editor)
    Article.objects.filter(pk=article.pk).update(version=3)
    client.force_login(editor)
    payload = article_payload(version=2, title="旧窗口里的内容")

    response = post_json(
        client,
        reverse("studio:api_article_autosave", args=(article.pk,)),
        payload,
    )
    article.refresh_from_db()

    assert response.status_code == 409
    assert response.json()["code"] == "version_conflict"
    assert response.json()["current_version"] == 3
    assert article.title == "服务器上的版本"
    assert article.version == 3


def test_publish_freezes_public_snapshot_and_records_one_publish_revision(client):
    editor = backend_user()
    article = Article.objects.create(title="发布前", slug="publish-article", author=editor)
    client.force_login(editor)
    payload = article_payload(version=0, title="正式发布", text="这是发布版本")

    response = post_json(
        client,
        reverse("studio:api_article_publish", args=(article.pk,)),
        payload,
    )
    article.refresh_from_db()

    assert response.status_code == 200
    assert article.status == Article.Status.PUBLISHED
    assert article.version == 2
    assert article.published_title == "正式发布"
    assert article.published_body_text == "这是发布版本"
    assert list(article.revisions.values_list("action", flat=True)) == [
        ContentRevision.Action.PUBLISH
    ]
    assert AuditEvent.objects.filter(action=AuditEvent.Action.PUBLISH).count() == 1


def test_publish_rolls_back_content_and_revision_when_audit_fails(client):
    editor = backend_user()
    article = Article.objects.create(title="仍是草稿", slug="rollback", author=editor)
    client.force_login(editor)
    payload = article_payload(version=0, title="不应发布", text="不应写入")

    with (
        patch("studio.api.articles.record_content_event", side_effect=RuntimeError("audit failed")),
        pytest.raises(RuntimeError, match="audit failed"),
    ):
        post_json(
            client,
            reverse("studio:api_article_publish", args=(article.pk,)),
            payload,
        )
    article.refresh_from_db()

    assert article.title == "仍是草稿"
    assert article.status == Article.Status.DRAFT
    assert article.version == 0
    assert article.published_body_json is None
    assert article.revisions.count() == 0
    assert not SearchDocument.objects.filter(kind="article", object_id=article.pk).exists()
    assert not Event.objects.filter(event_type=Event.EventType.CONTENT_PUBLISHED).exists()


def test_preview_uses_server_rendered_safe_html(client):
    editor = backend_user()
    article = Article.objects.create(
        title="安全预览",
        slug="safe-preview",
        author=editor,
        body_json=document('<script>alert("x")</script>'),
    )
    client.force_login(editor)

    response = client.get(reverse("studio:article_preview", args=(article.pk,)))
    body = response.content.decode()

    assert response.status_code == 200
    assert "<script>alert" not in body
    assert "&lt;script&gt;alert" in body
    assert "访客看不到" in body


def test_article_api_requires_csrf():
    editor = backend_user()
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(editor)

    response = post_json(
        csrf_client,
        reverse("studio:api_article_create"),
        article_payload() | {"intent": "autosave"},
    )

    assert response.status_code == 403
    assert Article.objects.count() == 0
