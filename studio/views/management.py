from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import Group
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import User
from accounts.services import change_membership_level
from publishing.models import SiteProfile
from studio.forms.management import SiteProfileForm, UserManagementForm
from studio.models import AuditEvent
from studio.permissions import (
    OWNER_ROLES,
    ROLE_GROUPS,
    ROLE_LABELS,
    StudioRole,
    get_studio_role,
    studio_context,
    studio_role_required,
)


def _role_value(user):
    role = get_studio_role(user)
    return role.value if role else ""


@studio_role_required(*OWNER_ROLES)
def user_list(request):
    query = request.GET.get("q", "").strip()
    level = request.GET.get("level", "").strip()
    status = request.GET.get("status", "").strip()
    users = User.objects.prefetch_related("groups").order_by("-date_joined", "-pk")
    if query:
        users = users.filter(Q(email__icontains=query) | Q(display_name__icontains=query))
    if level in User.MembershipLevel.values:
        users = users.filter(membership_level=level)
    if status == "active":
        users = users.filter(is_active=True)
    elif status == "inactive":
        users = users.filter(is_active=False)

    page = Paginator(users, 30).get_page(request.GET.get("page"))
    for user in page.object_list:
        role = get_studio_role(user)
        user.studio_role_label = ROLE_LABELS.get(role, "无后台权限")

    context = studio_context(request.user)
    context.update(
        {
            "studio_section": "users",
            "users_page": page,
            "query": query,
            "selected_level": level,
            "selected_status": status,
            "membership_choices": User.MembershipLevel.choices,
            "user_metrics": {
                "all": User.objects.count(),
                "active": User.objects.filter(is_active=True).count(),
                "pending": User.objects.filter(
                    membership_level=User.MembershipLevel.PENDING
                ).count(),
                "backend": User.objects.filter(
                    Q(is_superuser=True) | Q(groups__name__in=ROLE_GROUPS.values())
                )
                .distinct()
                .count(),
            },
        }
    )
    return render(request, "studio/users/list.html", context)


@studio_role_required(*OWNER_ROLES)
def user_edit(request, pk):
    target = get_object_or_404(User.objects.prefetch_related("groups"), pk=pk)
    form = UserManagementForm(
        request.POST or None,
        target_user=target,
        actor=request.user,
    )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            before = {
                "membership_level": target.membership_level,
                "studio_role": _role_value(target),
                "is_active": target.is_active,
            }
            requested_level = form.cleaned_data["membership_level"]
            if requested_level != target.membership_level:
                change_membership_level(
                    user=target,
                    to_level=requested_level,
                    reason=form.cleaned_data["reason"],
                    actor=request.user,
                )

            requested_role = form.cleaned_data["studio_role"]
            role_groups = list(Group.objects.filter(name__in=ROLE_GROUPS.values()))
            if not target.is_superuser:
                target.groups.remove(*role_groups)
                if requested_role:
                    target.groups.add(
                        Group.objects.get(
                            name=ROLE_GROUPS[StudioRole(requested_role)]
                        )
                    )

            requested_active = form.cleaned_data["is_active"]
            if target.is_active != requested_active:
                target.is_active = requested_active
                target.save(update_fields=("is_active",))

            after = {
                "membership_level": target.membership_level,
                "studio_role": (
                    StudioRole.OWNER.value
                    if target.is_superuser
                    else requested_role
                ),
                "is_active": target.is_active,
            }
            AuditEvent.objects.create(
                actor=request.user,
                action=AuditEvent.Action.USER_UPDATE,
                object_type="user",
                object_id=str(target.pk),
                object_label=target.display_name or target.email,
                reason=form.cleaned_data["reason"],
                metadata={"before": before, "after": after},
            )
        messages.success(request, "用户权限和会员等级已更新。")
        return redirect("studio:users")

    context = studio_context(request.user)
    context.update(
        {
            "studio_section": "users",
            "target_user": target,
            "form": form,
        }
    )
    return render(request, "studio/users/edit.html", context)


@studio_role_required(*OWNER_ROLES)
def site_settings(request):
    profile = SiteProfile.objects.first()
    instance = profile or SiteProfile()
    form = SiteProfileForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            saved = form.save()
            AuditEvent.objects.create(
                actor=request.user,
                action=AuditEvent.Action.SITE_SETTINGS_UPDATE,
                object_type="site_profile",
                object_id=str(saved.pk),
                object_label=saved.site_name,
                reason="更新网站基础资料",
                metadata={"changed_fields": list(form.changed_data)},
            )
        messages.success(request, "网站设置已保存并立即生效。")
        return redirect("studio:settings")

    context = studio_context(request.user)
    context.update(
        {
            "studio_section": "settings",
            "form": form,
            "site_profile": profile,
            "public_site_origin": settings.PUBLIC_SITE_ORIGIN,
        }
    )
    return render(request, "studio/settings/site.html", context)
