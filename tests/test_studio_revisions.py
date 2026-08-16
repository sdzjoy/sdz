from datetime import timedelta
from io import StringIO

import pytest
from allauth.mfa.models import Authenticator
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from publishing.models import Article, ContentEntry, ContentRevision
from publishing.services import move_to_trash, save_draft
from studio.models import AuditEvent
from studio.permissions import ROLE_GROUPS, StudioRole

pytestmark = pytest.mark.django_db
TEST_PASSWORD = "a-safe-test-password"  # noqa: S105


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


def backend_user(role=StudioRole.EDITOR, email="revision-editor@example.com"):
    user = User.objects.create_user(email, TEST_PASSWORD)
    user.groups.add(Group.objects.get(name=ROLE_GROUPS[role]))
    Authenticator.objects.create(
        user=user,
        type=Authenticator.Type.TOTP,
        data={"secret": "encrypted-test-placeholder"},
    )
    return user


def changed_article(actor):
    article = Article.objects.create(
        title="初始标题",
        slug="revision-history",
        summary="不应泄露完整快照",
        body_json=document("仅在预览中出现的旧正文"),
        author=actor,
    )
    return save_draft(
        article,
        expected_version=0,
        actor=actor,
        title="当前标题",
        slug=article.slug,
        summary="当前摘要",
        body_json=document("当前正文"),
        revision_summary="补充冷源说明",
    )


def test_revision_list_only_exposes_metadata_and_links_to_preview(client):
    editor = backend_user()
    article = changed_article(editor)
    revision = article.revisions.get()
    client.force_login(editor)

    response = client.get(reverse("studio:revision_list", args=(article.pk,)))
    body = response.content.decode()

    assert response.status_code == 200
    assert editor.email in body
    assert "手工保存前" in body
    assert "补充冷源说明" in body
    assert "仅在预览中出现的旧正文" not in body
    assert reverse("studio:revision_preview", args=(article.pk, revision.pk)) in body
    assert response["Cache-Control"] == "private, no-store"


def test_revision_preview_uses_safe_server_rendering(client):
    editor = backend_user()
    article = Article.objects.create(
        title="危险字符",
        slug="safe-revision",
        body_json=document('<script>alert("old")</script>'),
        author=editor,
    )
    article = save_draft(
        article,
        expected_version=0,
        actor=editor,
        title="当前版本",
        slug=article.slug,
        summary="",
        body_json=document("当前正文"),
    )
    revision = article.revisions.get()
    client.force_login(editor)

    response = client.get(
        reverse("studio:revision_preview", args=(article.pk, revision.pk))
    )
    body = response.content.decode()

    assert response.status_code == 200
    assert "<script>alert" not in body
    assert "&lt;script&gt;alert" in body
    assert f'name="version" value="{article.version}"' in body


def test_restore_creates_pre_restore_revision_and_audit_and_is_undoable(client):
    editor = backend_user()
    article = changed_article(editor)
    old_revision = article.revisions.get(number=1)
    client.force_login(editor)

    response = client.post(
        reverse("studio:revision_restore", args=(article.pk, old_revision.pk)),
        {"version": article.version},
    )
    article.refresh_from_db()

    assert response.status_code == 302
    assert article.title == "初始标题"
    assert article.body_text == "仅在预览中出现的旧正文"
    assert article.version == 2
    pre_restore = article.revisions.get(number=2)
    assert pre_restore.action == ContentRevision.Action.RESTORE
    assert pre_restore.snapshot["common"]["title"] == "当前标题"
    audit = AuditEvent.objects.get(action=AuditEvent.Action.RESTORE_REVISION)
    assert audit.actor == editor
    assert audit.metadata == {"restored_revision": 1}

    second_response = client.post(
        reverse("studio:revision_restore", args=(article.pk, pre_restore.pk)),
        {"version": article.version},
    )
    article.refresh_from_db()

    assert second_response.status_code == 302
    assert article.title == "当前标题"
    assert article.body_text == "当前正文"
    assert article.version == 3


def test_stale_restore_returns_conflict_without_overwriting(client):
    editor = backend_user()
    article = changed_article(editor)
    revision = article.revisions.get(number=1)
    client.force_login(editor)

    response = client.post(
        reverse("studio:revision_restore", args=(article.pk, revision.pk)),
        {"version": 0},
    )
    article.refresh_from_db()

    assert response.status_code == 409
    assert response["X-Current-Content-Version"] == "1"
    assert article.title == "当前标题"
    assert article.revisions.count() == 1
    assert not AuditEvent.objects.filter(
        action=AuditEvent.Action.RESTORE_REVISION
    ).exists()


def test_restore_requires_post_and_csrf():
    editor = backend_user()
    article = changed_article(editor)
    revision = article.revisions.get()
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(editor)
    url = reverse("studio:revision_restore", args=(article.pk, revision.pk))

    assert csrf_client.get(url).status_code == 405
    assert csrf_client.post(url, {"version": article.version}).status_code == 403


def test_purge_command_is_preview_only_by_default_and_respects_thirty_days():
    owner = User.objects.create_superuser("purge-owner@example.com", TEST_PASSWORD)
    old = Article.objects.create(title="旧内容", slug="old-purge", author=owner)
    recent = Article.objects.create(title="近期内容", slug="recent-purge", author=owner)
    old = move_to_trash(old, expected_version=0, actor=owner)
    move_to_trash(recent, expected_version=0, actor=owner)
    ContentEntry.objects.filter(pk=old.pk).update(
        deleted_at=timezone.now() - timedelta(days=31)
    )
    output = StringIO()

    call_command("purge_deleted_content", stdout=output)

    assert "共有 1 项" in output.getvalue()
    assert "未删除任何内容" in output.getvalue()
    assert ContentEntry.objects.filter(pk__in=[old.pk, recent.pk]).count() == 2


def test_purge_command_requires_owner_and_audits_actual_delete():
    owner = User.objects.create_superuser("purge-execute@example.com", TEST_PASSWORD)
    editor = backend_user(email="purge-editor@example.com")
    old = Article.objects.create(title="待清理内容", slug="purge-now", author=owner)
    old = move_to_trash(old, expected_version=0, actor=owner)
    ContentEntry.objects.filter(pk=old.pk).update(
        deleted_at=timezone.now() - timedelta(days=31)
    )

    with pytest.raises(CommandError, match="只有站长账号"):
        call_command(
            "purge_deleted_content",
            execute=True,
            actor_email=editor.email,
        )

    output = StringIO()
    call_command(
        "purge_deleted_content",
        execute=True,
        actor_email=owner.email,
        reason="确认清理过期测试内容",
        stdout=output,
    )

    assert "已永久清理 1 项" in output.getvalue()
    assert not ContentEntry.objects.filter(pk=old.pk).exists()
    audit = AuditEvent.objects.get(action=AuditEvent.Action.PERMANENT_DELETE)
    assert audit.actor == owner
    assert audit.object_id == str(old.pk)
    assert audit.reason == "确认清理过期测试内容"
    assert audit.metadata["source"] == "purge_deleted_content"
