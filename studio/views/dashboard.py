from django.db.models import Count
from django.shortcuts import render

from publishing.models import ContentEntry, Note

from ..permissions import (
    CONTENT_ROLES,
    RESOURCE_ROLES,
    StudioRole,
    get_studio_role,
    studio_context,
    studio_role_required,
)

PLACEHOLDERS = {
    "resources": ("网盘资源", "现有资源库将在后续改接到这个入口。", RESOURCE_ROLES),
}


@studio_role_required(*StudioRole)
def dashboard(request):
    role = get_studio_role(request.user)
    context = studio_context(request.user)
    context["studio_section"] = "dashboard"

    if role in CONTENT_ROLES:
        active = ContentEntry.objects.active()
        context.update(
            {
                "recent_drafts": active.filter(status=ContentEntry.Status.DRAFT)
                .select_related("author")[:6],
                "recent_published": active.filter(status=ContentEntry.Status.PUBLISHED)
                .select_related("author")
                .order_by("-published_at", "-pk")[:6],
                "pending_note_count": Note.objects.active()
                .filter(promoted_article__isnull=True)
                .count(),
                "trash_count": ContentEntry.objects.in_trash().count(),
                "content_counts": {
                    row["kind"]: row["count"]
                    for row in active.values("kind").annotate(count=Count("pk"))
                },
            }
        )
    return render(request, "studio/dashboard.html", context)


def placeholder(request, section, **kwargs):
    title, description, allowed_roles = PLACEHOLDERS[section]
    role = get_studio_role(request.user)
    if role is None or role not in allowed_roles:
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied
    context = studio_context(request.user)
    context.update(
        {
            "studio_section": section,
            "placeholder_title": title,
            "placeholder_description": description,
        }
    )
    return render(request, "studio/placeholder.html", context)
