from collections.abc import Callable
from enum import StrEnum
from functools import wraps

from django.core.exceptions import PermissionDenied


class StudioRole(StrEnum):
    OWNER = "owner"
    EDITOR = "editor"
    RESOURCE_ADMIN = "resource_admin"


ROLE_GROUPS = {
    StudioRole.OWNER: "studio-owner",
    StudioRole.EDITOR: "studio-editor",
    StudioRole.RESOURCE_ADMIN: "studio-resource-admin",
}
ROLE_LABELS = {
    StudioRole.OWNER: "站长",
    StudioRole.EDITOR: "编辑",
    StudioRole.RESOURCE_ADMIN: "资料管理员",
}
CONTENT_ROLES = frozenset({StudioRole.OWNER, StudioRole.EDITOR})
RESOURCE_ROLES = frozenset(
    {StudioRole.OWNER, StudioRole.EDITOR, StudioRole.RESOURCE_ADMIN}
)
OWNER_ROLES = frozenset({StudioRole.OWNER})


def get_studio_role(user) -> StudioRole | None:
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return None
    cached = getattr(user, "_studio_role", None)
    if cached is not None:
        return cached
    if user.is_superuser:
        role = StudioRole.OWNER
    else:
        group_names = set(
            user.groups.filter(name__in=ROLE_GROUPS.values()).values_list("name", flat=True)
        )
        role = next(
            (candidate for candidate, group in ROLE_GROUPS.items() if group in group_names),
            None,
        )
    user._studio_role = role
    return role


def studio_context(user) -> dict[str, object]:
    role = get_studio_role(user)
    return {
        "studio_role": role,
        "studio_role_label": ROLE_LABELS.get(role, ""),
        "studio_can_edit_content": role in CONTENT_ROLES,
        "studio_can_manage_resources": role in RESOURCE_ROLES,
        "studio_is_owner": role in OWNER_ROLES,
    }


def studio_role_required(*allowed_roles: StudioRole) -> Callable:
    allowed = frozenset(allowed_roles)

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            role = get_studio_role(request.user)
            if role is None or (allowed and role not in allowed):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator
