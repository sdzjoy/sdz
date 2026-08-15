import pytest

from accounts.models import User


@pytest.mark.django_db
def test_regular_user_uses_normalized_email_and_starts_pending():
    user = User.objects.create_user("Person@Example.COM", "a-safe-test-password")

    assert user.email == "person@example.com"
    assert user.membership_level == User.MembershipLevel.PENDING
    assert user.check_password("a-safe-test-password")
    assert not user.is_staff


@pytest.mark.django_db
def test_superuser_is_owner():
    user = User.objects.create_superuser("owner@example.com", "a-safe-test-password")

    assert user.membership_level == User.MembershipLevel.OWNER
    assert user.is_staff
    assert user.is_superuser


@pytest.mark.django_db
def test_user_requires_email():
    with pytest.raises(ValueError, match="邮箱不能为空"):
        User.objects.create_user("", "a-safe-test-password")
