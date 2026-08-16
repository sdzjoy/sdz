from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from resources.models import Resource
from standards.models import Standard

from ..permissions import CONTENT_ROLES, studio_role_required


@require_GET
@studio_role_required(*CONTENT_ROLES)
def reference_search(request):
    kind = request.GET.get("kind", "")
    query = request.GET.get("q", "").strip()[:120]
    if kind == "standard":
        items = Standard.objects.order_by("code")
        if query:
            items = items.filter(Q(code__icontains=query) | Q(title_cn__icontains=query))
        results = [
            {
                "id": item.pk,
                "label": item.code,
                "description": f"{item.title_cn} · {item.get_status_display()}",
            }
            for item in items[:20]
        ]
    elif kind == "resource":
        items = Resource.objects.filter(status=Resource.Status.PUBLISHED).order_by("title")
        if query:
            items = items.filter(Q(title__icontains=query) | Q(summary__icontains=query))
        results = [
            {
                "id": item.pk,
                "label": item.title,
                "description": item.get_access_level_display(),
            }
            for item in items[:20]
        ]
    else:
        return JsonResponse(
            {"ok": False, "code": "invalid_kind", "message": "引用类型无效。"},
            status=400,
        )
    return JsonResponse({"ok": True, "items": results})
