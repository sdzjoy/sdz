import pytest
from allauth.mfa.models import Authenticator
from django.contrib.auth.models import Group
from django.urls import reverse

from accounts.models import User
from publishing.models import Article
from studio.permissions import ROLE_GROUPS, StudioRole, get_studio_role

pytestmark = pytest.mark.django_db
TEST_PASSWORD = "a-safe-test-password"  # noqa: S105


def user_with_role(role, *, email="editor@example.com", mfa=True, membership="L0"):
    user = User.objects.create_user(
        email,
        TEST_PASSWORD,
        membership_level=membership,
    )
    user.groups.add(Group.objects.get(name=ROLE_GROUPS[role]))
    if mfa:
        Authenticator.objects.create(
            user=user,
            type=Authenticator.Type.TOTP,
            data={"secret": "encrypted-test-placeholder"},
        )
    return user


def test_anonymous_studio_request_redirects_to_login(client):
    response = client.get(reverse("studio:dashboard"))

    assert response.status_code == 302
    assert response.url.startswith("/account/login/?")
    assert "next=%2Fcms%2F" in response.url


def test_membership_level_does_not_grant_backend_access(client):
    member = User.objects.create_user(
        "member-owner-level@example.com",
        TEST_PASSWORD,
        membership_level=User.MembershipLevel.OWNER,
    )
    Authenticator.objects.create(
        user=member,
        type=Authenticator.Type.TOTP,
        data={"secret": "encrypted-test-placeholder"},
    )
    client.force_login(member)

    response = client.get(reverse("studio:dashboard"))

    assert response.status_code == 403
    assert get_studio_role(member) is None


def test_backend_role_requires_mfa_before_dashboard_access(client):
    editor = user_with_role(StudioRole.EDITOR, mfa=False)
    client.force_login(editor)

    response = client.get(reverse("studio:dashboard"))

    assert response.status_code == 302
    assert response.url == reverse("mfa_index")


def test_editor_can_open_dashboard_without_django_staff_flag(client):
    editor = user_with_role(StudioRole.EDITOR)
    Article.objects.create(
        title="正在整理的数据中心冷源文章",
        slug="draft-cooling-source",
        author=editor,
    )
    client.force_login(editor)

    response = client.get(reverse("studio:dashboard"))
    body = response.content.decode()

    assert response.status_code == 200
    assert editor.is_staff is False
    assert "今天准备写点什么" in body
    assert "正在整理的数据中心冷源文章" in body
    assert "写文章" in body
    assert "用户" not in body
    assert response["Cache-Control"] == "private, no-store"
    assert response["Pragma"] == "no-cache"


def test_resource_admin_sees_resource_entry_but_not_content_actions(client):
    resource_admin = user_with_role(
        StudioRole.RESOURCE_ADMIN,
        email="resource-admin@example.com",
    )
    client.force_login(resource_admin)

    response = client.get(reverse("studio:dashboard"))
    body = response.content.decode()

    assert response.status_code == 200
    assert "从资料库开始" in body
    assert "进入资料库" in body
    assert "写文章" not in body
    assert 'href="/cms/content/"' not in body


def test_superuser_is_owner_and_sees_all_primary_navigation(client):
    owner = User.objects.create_superuser("owner@example.com", TEST_PASSWORD)
    Authenticator.objects.create(
        user=owner,
        type=Authenticator.Type.TOTP,
        data={"secret": "encrypted-test-placeholder"},
    )
    client.force_login(owner)

    response = client.get(reverse("studio:dashboard"))
    body = response.content.decode()

    assert response.status_code == 200
    assert get_studio_role(owner) == StudioRole.OWNER
    for label in ("首页", "内容", "资料库", "用户", "设置"):
        assert label in body


def test_legacy_wagtail_admin_remains_mfa_protected_during_compatibility(client):
    staff = User.objects.create_user(
        "legacy-staff@example.com",
        TEST_PASSWORD,
        is_staff=True,
    )
    client.force_login(staff)

    response = client.get("/legacy-cms/")

    assert response.status_code == 302
    assert response.url == reverse("mfa_index")
