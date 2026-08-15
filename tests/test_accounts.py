from unittest.mock import Mock, patch

import pytest
from allauth.account.models import EmailAddress, EmailConfirmationHMAC
from allauth.account.signals import email_confirmed
from allauth.idp.oidc.models import Client
from allauth.mfa.models import Authenticator
from django.core import mail
from django.core.exceptions import PermissionDenied
from django.test import override_settings
from django.urls import reverse

from accounts.adapters import EncryptedMFAAdapter
from accounts.forms import SignupExtraForm
from accounts.models import AccountRequest, MembershipChange, User
from accounts.services import change_membership_level

TEST_PASSWORD = "a-safe-test-password"  # noqa: S105
TEST_CLIENT_SECRET = "one-time-client-secret"  # noqa: S105
TEST_TURNSTILE_SECRET = "test-secret"  # noqa: S105


def create_verified_user(email="member@example.com", password=None):
    password = password or TEST_PASSWORD
    user = User.objects.create_user(email, password, display_name="测试会员")
    address = EmailAddress.objects.create(
        user=user,
        email=user.email,
        primary=True,
        verified=False,
    )
    address.verified = True
    address.save(update_fields=("verified",))
    email_confirmed.send(
        sender=EmailAddress,
        request=None,
        email_address=address,
    )
    user.refresh_from_db()
    return user


@pytest.mark.django_db
def test_signup_stays_l0_until_email_is_confirmed(client):
    response = client.post(
        reverse("account_signup"),
        {
            "email": "new@example.com",
            "display_name": "新会员",
            "password1": "a-safe-test-password",
            "password2": "a-safe-test-password",
            "turnstile_token": "",
        },
    )

    assert response.status_code == 302
    user = User.objects.get(email="new@example.com")
    assert user.membership_level == User.MembershipLevel.PENDING
    assert user.email_verified_at is None
    assert not MembershipChange.objects.filter(user=user).exists()
    assert len(mail.outbox) == 1

    address = EmailAddress.objects.get(user=user)
    confirmation = EmailConfirmationHMAC(address)
    response = client.post(reverse("account_confirm_email", args=[confirmation.key]))
    assert response.status_code == 302

    user.refresh_from_db()
    assert user.membership_level == User.MembershipLevel.MEMBER
    assert user.email_verified_at is not None
    change = MembershipChange.objects.get(user=user)
    assert change.from_level == User.MembershipLevel.PENDING
    assert change.to_level == User.MembershipLevel.MEMBER
    assert change.changed_by is None


@pytest.mark.django_db
def test_unverified_account_cannot_log_in_as_l1(client):
    User.objects.create_user("pending@example.com", "a-safe-test-password")

    response = client.post(
        reverse("account_login"),
        {"login": "pending@example.com", "password": "a-safe-test-password"},
    )

    assert response.status_code == 302
    assert response.url == reverse("account_email_verification_sent")
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_membership_elevation_requires_another_staff_user():
    member = create_verified_user()

    with pytest.raises(PermissionDenied):
        change_membership_level(
            user=member,
            to_level=User.MembershipLevel.TRUSTED,
            reason="尝试自行升级",
            actor=member,
        )

    owner = User.objects.create_superuser("owner@example.com", "a-safe-test-password")
    change = change_membership_level(
        user=member,
        to_level=User.MembershipLevel.TRUSTED,
        reason="人工核验通过",
        actor=owner,
    )

    member.refresh_from_db()
    assert member.membership_level == User.MembershipLevel.TRUSTED
    assert change.changed_by == owner
    assert change.reason == "人工核验通过"


@pytest.mark.django_db
def test_staff_cannot_enter_admin_without_mfa(client):
    owner = User.objects.create_superuser("owner@example.com", "a-safe-test-password")
    client.force_login(owner)

    response = client.get("/cms/")

    assert response.status_code == 302
    assert response.url == reverse("mfa_index")

    Authenticator.objects.create(
        user=owner,
        type=Authenticator.Type.TOTP,
        data={"secret": "encrypted-test-placeholder"},
    )
    response = client.get("/cms/")
    assert response.status_code == 200


@override_settings(MFA_ENCRYPTION_KEY="separate-test-encryption-key")
def test_mfa_secrets_are_encrypted_at_rest():
    adapter = EncryptedMFAAdapter()

    encrypted = adapter.encrypt("totp-secret-value")

    assert encrypted != "totp-secret-value"
    assert "totp-secret-value" not in encrypted
    assert adapter.decrypt(encrypted) == "totp-secret-value"


@pytest.mark.django_db
def test_oidc_client_uses_exact_callback_and_hashed_secret(settings):
    client = Client.objects.create(
        name="HVAC",
        scopes="openid\nprofile\nemail\nmembership",
        redirect_uris="https://hvac.sdzjoy.com/account/callback/",
        grant_types=Client.GrantType.AUTHORIZATION_CODE,
        response_types=Client.ResponseType.CODE,
        allow_uri_wildcards=False,
    )
    client.set_secret(TEST_CLIENT_SECRET)
    client.save(update_fields=("secret",))

    assert client.get_redirect_uris() == [
        "https://hvac.sdzjoy.com/account/callback/"
    ]
    assert client.secret != TEST_CLIENT_SECRET
    assert client.check_secret(TEST_CLIENT_SECRET)
    assert settings.IDP_OIDC_AUTHORIZATION_CODE_EXPIRES_IN == 60
    assert settings.IDP_OIDC_DCR_ENABLED is False


@override_settings(
    TURNSTILE_REQUIRED=True,
    TURNSTILE_SECRET_KEY=TEST_TURNSTILE_SECRET,
    TURNSTILE_EXPECTED_HOSTNAMES=["id.sdzjoy.com"],
)
def test_turnstile_validation_checks_action_and_hostname():
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "success": True,
        "action": "signup",
        "hostname": "id.sdzjoy.com",
    }
    with patch("accounts.security.requests.post", return_value=response):
        form = SignupExtraForm(
            {"display_name": "测试会员", "turnstile_token": "test-token"}
        )

        assert form.is_valid()


@pytest.mark.django_db
def test_account_export_and_delete_request_require_recent_authentication(client):
    user = create_verified_user()
    response = client.post(
        reverse("account_login"),
        {"login": user.email, "password": "a-safe-test-password"},
    )
    assert response.status_code == 302

    export = client.post(reverse("account_export"))
    assert export.status_code == 200
    assert export.json()["account"]["email"] == user.email
    assert export["Cache-Control"] == "private, no-store"

    first = client.post(reverse("account_delete_request"))
    second = client.post(reverse("account_delete_request"))
    assert first.status_code == 302
    assert second.status_code == 302
    assert (
        AccountRequest.objects.filter(
            user=user,
            request_type=AccountRequest.RequestType.DELETE,
            status=AccountRequest.Status.PENDING,
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_verified_user_can_deactivate_their_account(client):
    user = create_verified_user("leaving@example.com")
    client.post(
        reverse("account_login"),
        {"login": user.email, "password": TEST_PASSWORD},
    )

    response = client.post(reverse("account_deactivate"))

    user.refresh_from_db()
    assert response.status_code == 302
    assert response.url == "/"
    assert user.is_active is False
    assert "_auth_user_id" not in client.session
    request = AccountRequest.objects.get(
        user=user,
        request_type=AccountRequest.RequestType.DEACTIVATE,
    )
    assert request.status == AccountRequest.Status.COMPLETED
    assert request.processed_at is not None
