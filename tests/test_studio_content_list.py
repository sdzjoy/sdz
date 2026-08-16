from datetime import timedelta

import pytest
from allauth.mfa.models import Authenticator
from django.contrib.auth.models import Group
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from publishing.models import Article, ContentEntry, Project, Topic
from publishing.services import move_to_trash
from studio.models import AuditEvent
from studio.permissions import ROLE_GROUPS, StudioRole

pytestmark = pytest.mark.django_db
TEST_PASSWORD = "a-safe-test-password"  # noqa: S105


def backend_user(role=StudioRole.EDITOR, email="editor@example.com"):
    user = User.objects.create_user(email, TEST_PASSWORD)
    user.groups.add(Group.objects.get(name=ROLE_GROUPS[role]))
    Authenticator.objects.create(
        user=user,
        type=Authenticator.Type.TOTP,
        data={"secret": "encrypted-test-placeholder"},
    )
    return user


def test_content_list_searches_filters_and_prefetches_topics(client):
    editor = backend_user()
    cooling = Topic.objects.create(name="冷源", slug="cooling")
    target = Article.objects.create(
        title="液冷机房设计",
        slug="liquid-room",
        summary="液冷系统",
        author=editor,
    )
    target.topics.add(cooling)
    Article.objects.create(title="气流组织", slug="airflow", author=editor)
    Project.objects.create(title="机房项目", slug="project", author=editor)
    client.force_login(editor)

    response = client.get(
        reverse("studio:content_list"),
        {"q": "液冷", "kind": "article", "topic": cooling.pk},
    )
    body = response.content.decode()

    assert response.status_code == 200
    assert "液冷机房设计" in body
    assert "气流组织" not in body
    assert "机房项目" not in body
    assert "冷源" in body

    with CaptureQueriesContext(connection) as queries:
        response = client.get(reverse("studio:content_list"), {"kind": "article"})
        assert response.status_code == 200
    assert len(queries) <= 15


def test_bulk_publish_and_trash_use_domain_services_and_audit(client):
    editor = backend_user()
    first = Article.objects.create(title="第一篇", slug="first", author=editor)
    second = Article.objects.create(title="第二篇", slug="second", author=editor)
    client.force_login(editor)

    publish_response = client.post(
        reverse("studio:content_bulk_action"),
        {"action": "publish", "selected": [first.pk, second.pk]},
    )

    assert publish_response.status_code == 302
    assert ContentEntry.objects.published().filter(pk__in=[first.pk, second.pk]).count() == 2
    assert AuditEvent.objects.filter(action=AuditEvent.Action.BULK_PUBLISH).count() == 2

    first.refresh_from_db()
    trash_response = client.post(
        reverse("studio:content_bulk_action"),
        {"action": "trash", "selected": [first.pk]},
    )
    first.refresh_from_db()

    assert trash_response.status_code == 302
    assert first.deleted_at is not None
    assert first.revisions.count() == 2
    assert AuditEvent.objects.filter(action=AuditEvent.Action.MOVE_TO_TRASH).count() == 1


def test_bulk_write_requires_csrf():
    editor = backend_user()
    article = Article.objects.create(title="CSRF", slug="csrf", author=editor)
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(editor)

    response = csrf_client.post(
        reverse("studio:content_bulk_action"),
        {"action": "trash", "selected": [article.pk]},
    )

    assert response.status_code == 403
    article.refresh_from_db()
    assert article.deleted_at is None


def test_resource_admin_cannot_open_content_list(client):
    resource_admin = backend_user(
        StudioRole.RESOURCE_ADMIN,
        email="resource@example.com",
    )
    client.force_login(resource_admin)

    assert client.get(reverse("studio:content_list")).status_code == 403


def test_trash_restore_and_permanent_delete_rules(client):
    owner = User.objects.create_superuser("owner@example.com", TEST_PASSWORD)
    Authenticator.objects.create(
        user=owner,
        type=Authenticator.Type.TOTP,
        data={"secret": "encrypted-test-placeholder"},
    )
    restorable = Article.objects.create(title="可恢复", slug="restore", author=owner)
    old = Article.objects.create(title="旧回收项", slug="old-trash", author=owner)
    restorable = move_to_trash(restorable, expected_version=0, actor=owner)
    old = move_to_trash(old, expected_version=0, actor=owner)
    ContentEntry.objects.filter(pk=old.pk).update(
        deleted_at=timezone.now() - timedelta(days=31)
    )
    client.force_login(owner)

    restore_response = client.post(reverse("studio:content_restore", args=(restorable.pk,)))
    restorable.refresh_from_db()

    assert restore_response.status_code == 302
    assert restorable.deleted_at is None
    assert AuditEvent.objects.filter(action=AuditEvent.Action.RESTORE_FROM_TRASH).exists()

    recent = Article.objects.create(title="未满三十天", slug="recent-trash", author=owner)
    recent = move_to_trash(recent, expected_version=0, actor=owner)
    too_early = client.post(
        reverse("studio:content_permanent_delete", args=(recent.pk,)),
        {"reason": "确认不再需要"},
    )
    assert too_early.status_code == 403

    deleted_id = old.pk
    delete_response = client.post(
        reverse("studio:content_permanent_delete", args=(old.pk,)),
        {"reason": "重复的测试内容，确认删除"},
    )

    assert delete_response.status_code == 302
    assert not ContentEntry.objects.filter(pk=deleted_id).exists()
    audit = AuditEvent.objects.get(action=AuditEvent.Action.PERMANENT_DELETE)
    assert audit.object_id == str(deleted_id)
    assert audit.reason == "重复的测试内容，确认删除"


def test_editor_cannot_permanently_delete_even_old_trash(client):
    editor = backend_user()
    article = Article.objects.create(title="保留", slug="keep", author=editor)
    trashed = move_to_trash(article, expected_version=0, actor=editor)
    ContentEntry.objects.filter(pk=trashed.pk).update(
        deleted_at=timezone.now() - timedelta(days=31)
    )
    client.force_login(editor)

    response = client.post(
        reverse("studio:content_permanent_delete", args=(trashed.pk,)),
        {"reason": "编辑无权永久删除"},
    )

    assert response.status_code == 403
    assert ContentEntry.objects.filter(pk=trashed.pk).exists()
