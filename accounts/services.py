from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .models import MembershipChange, User

LEVEL_RANK = {
    User.MembershipLevel.PENDING: 0,
    User.MembershipLevel.MEMBER: 1,
    User.MembershipLevel.TRUSTED: 2,
    User.MembershipLevel.OWNER: 3,
}


@transaction.atomic
def change_membership_level(*, user, to_level, reason, actor=None):
    if to_level not in LEVEL_RANK:
        raise ValidationError("未知会员等级。")
    reason = reason.strip()
    if not reason:
        raise ValidationError("会员等级变更必须填写原因。")

    locked_user = User.objects.select_for_update().get(pk=user.pk)
    from_level = locked_user.membership_level
    if from_level == to_level:
        return None

    is_email_activation = (
        actor is None
        and from_level == User.MembershipLevel.PENDING
        and to_level == User.MembershipLevel.MEMBER
        and locked_user.email_verified_at is not None
    )
    if not is_email_activation:
        if actor is None or not actor.is_active or not actor.is_staff:
            raise PermissionDenied("只有管理员可以调整会员等级。")
        if actor.pk == locked_user.pk and LEVEL_RANK[to_level] > LEVEL_RANK[from_level]:
            raise PermissionDenied("不能提升自己的会员等级。")

    locked_user.membership_level = to_level
    locked_user.save(update_fields=("membership_level",))
    change = MembershipChange.objects.create(
        user=locked_user,
        from_level=from_level,
        to_level=to_level,
        reason=reason,
        changed_by=actor,
    )
    user.membership_level = to_level
    return change
