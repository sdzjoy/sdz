from allauth.account.signals import email_confirmed
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import User
from .services import change_membership_level


@receiver(post_save, sender=User)
def ensure_owner_has_verified_email(sender, instance, created, **kwargs):
    if not instance.is_superuser or not instance.email_verified_at:
        return
    from allauth.account.models import EmailAddress

    EmailAddress.objects.update_or_create(
        user=instance,
        email=instance.email,
        defaults={"primary": True, "verified": True},
    )


@receiver(email_confirmed)
def activate_verified_member(request, email_address, **kwargs):
    user = email_address.user
    if user.email_verified_at is None:
        user.email_verified_at = timezone.now()
        user.save(update_fields=("email_verified_at",))
    if user.membership_level == User.MembershipLevel.PENDING:
        change_membership_level(
            user=user,
            to_level=User.MembershipLevel.MEMBER,
            reason="邮箱验证完成，系统自动启用普通会员权限。",
        )
