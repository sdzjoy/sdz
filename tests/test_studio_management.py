import pytest
from allauth.mfa.models import Authenticator
from django.contrib.auth.models import Group
from django.urls import reverse

from accounts.models import MembershipChange, User
from publishing.models import SiteProfile
from studio.models import AuditEvent
from studio.permissions import ROLE_GROUPS, StudioRole

pytestmark = pytest.mark.django_db
TEST_PASSWORD = "a-safe-test-password"  # noqa: S105


def owner_user(email="owner@example.com"):
    owner = User.objects.create_superuser(email, TEST_PASSWORD)
    Authenticator.objects.create(
        user=owner,
        type=Authenticator.Type.TOTP,
        data={"secret": "encrypted-test-placeholder"},
    )
    return owner


def studio_user(role=StudioRole.EDITOR, email="editor@example.com"):
    user = User.objects.create_user(email, TEST_PASSWORD)
    user.groups.add(Group.objects.get(name=ROLE_GROUPS[role]))
    Authenticator.objects.create(
        user=user,
        type=Authenticator.Type.TOTP,
        data={"secret": "encrypted-test-placeholder"},
    )
    return user


def test_owner_sees_real_user_management_page(client):
    owner = owner_user()
    member = User.objects.create_user(
        "member@example.com",
        TEST_PASSWORD,
        display_name="数据中心会员",
        membership_level=User.MembershipLevel.MEMBER,
    )
    client.force_login(owner)

    response = client.get(reverse("studio:users"))
    document = response.content.decode()

    assert response.status_code == 200
    assert member.email in document
    assert "数据中心会员" in document
    assert "普通会员" in document
    assert "用户与会员管理将在后续接入" not in document
    assert reverse("studio:user_edit", args=(member.pk,)) in document


def test_owner_can_update_membership_backend_role_and_active_state(client):
    owner = owner_user()
    member = User.objects.create_user("member@example.com", TEST_PASSWORD)
    client.force_login(owner)

    response = client.post(
        reverse("studio:user_edit", args=(member.pk,)),
        {
            "membership_level": User.MembershipLevel.TRUSTED,
            "studio_role": StudioRole.EDITOR,
            "is_active": "on",
            "reason": "已核验暖通从业信息",
        },
    )

    member.refresh_from_db()
    assert response.status_code == 302
    assert response.url == reverse("studio:users")
    assert member.membership_level == User.MembershipLevel.TRUSTED
    assert member.groups.filter(name=ROLE_GROUPS[StudioRole.EDITOR]).exists()
    assert MembershipChange.objects.get(user=member).changed_by == owner
    audit = AuditEvent.objects.get(action=AuditEvent.Action.USER_UPDATE)
    assert audit.actor == owner
    assert audit.object_id == str(member.pk)
    assert audit.reason == "已核验暖通从业信息"


def test_owner_cannot_deactivate_own_account_from_studio(client):
    owner = owner_user()
    client.force_login(owner)

    response = client.post(
        reverse("studio:user_edit", args=(owner.pk,)),
        {
            "membership_level": User.MembershipLevel.OWNER,
            "studio_role": StudioRole.OWNER,
            "reason": "误操作测试",
        },
    )

    owner.refresh_from_db()
    assert response.status_code == 200
    assert owner.is_active is True
    assert "不能停用当前登录账号" in response.content.decode()


def test_non_owner_cannot_open_user_or_site_settings(client):
    editor = studio_user()
    client.force_login(editor)

    assert client.get(reverse("studio:users")).status_code == 403
    assert client.get(reverse("studio:settings")).status_code == 403


def test_owner_can_edit_real_site_settings_and_change_is_audited(client):
    owner = owner_user()
    profile = SiteProfile.objects.create(site_name="修改前")
    client.force_login(owner)

    get_response = client.get(reverse("studio:settings"))
    assert get_response.status_code == 200
    assert "网站设置将在后续接入" not in get_response.content.decode()
    assert 'name="site_name"' in get_response.content.decode()

    response = client.post(
        reverse("studio:settings"),
        {
            "site_name": "少惰主暖通设计",
            "tagline": "数据中心暖通设计与工程资料",
            "owner_name": "少惰主",
            "article_intro": "数据中心暖通设计文章",
            "project_intro": "项目复盘",
            "note_intro": "设计随记",
            "tool_intro": "工程工具",
            "about_intro": "关于本站",
        },
    )

    profile.refresh_from_db()
    assert response.status_code == 302
    assert response.url == reverse("studio:settings")
    assert profile.site_name == "少惰主暖通设计"
    assert profile.tagline == "数据中心暖通设计与工程资料"
    audit = AuditEvent.objects.get(action=AuditEvent.Action.SITE_SETTINGS_UPDATE)
    assert audit.actor == owner
    assert audit.object_id == str(profile.pk)
