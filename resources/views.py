from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Resource, ResourceIssue, ResourceMirror


def _visible_resources(request):
    return Resource.objects.visible_to(request.user)


def resource_list(request):
    query = request.GET.get("q", "").strip()
    resources = _visible_resources(request).prefetch_related("taxonomies", "versions")
    if query:
        resources = resources.filter(
            Q(title__icontains=query)
            | Q(summary__icontains=query)
            | Q(author__icontains=query)
            | Q(file_format__icontains=query)
        )
    return render(
        request,
        "resources/resource_list.html",
        {"resources": resources.distinct(), "query": query},
    )


def _resource_with_visible_mirrors(request, slug):
    active_mirrors = ResourceMirror.objects.filter(status=ResourceMirror.Status.ACTIVE)
    return get_object_or_404(
        _visible_resources(request).prefetch_related(
            "taxonomies",
            "related_standards",
            "versions",
            Prefetch("mirrors", queryset=active_mirrors, to_attr="active_mirrors"),
        ),
        slug=slug,
    )


def _protect_restricted_response(response, resource):
    if resource.access_level != Resource.AccessLevel.PUBLIC:
        response["X-Robots-Tag"] = "noindex, nofollow"
    return response


def resource_detail(request, slug):
    resource = _resource_with_visible_mirrors(request, slug)
    response = render(
        request,
        "resources/resource_detail.html",
        {"resource": resource, "issue_choices": ResourceIssue.IssueType.choices},
    )
    return _protect_restricted_response(response, resource)


def resource_detail_json(request, slug):
    resource = _resource_with_visible_mirrors(request, slug)
    response = JsonResponse(
        {
            "title": resource.title,
            "slug": resource.slug,
            "summary": resource.summary,
            "access_level": resource.access_level,
            "copyright_status": resource.copyright_status,
            "versions": [
                {
                    "version": version.version,
                    "released_on": (
                        version.released_on.isoformat() if version.released_on else None
                    ),
                    "is_current": version.is_current,
                }
                for version in resource.versions.all()
            ],
            "mirrors": [
                {
                    "provider": mirror.get_provider_display(),
                    "share_url": mirror.share_url,
                    "extraction_code": mirror.extraction_code,
                    "last_verified_at": (
                        mirror.last_verified_at.isoformat()
                        if mirror.last_verified_at
                        else None
                    ),
                }
                for mirror in resource.active_mirrors
            ],
        },
        json_dumps_params={"ensure_ascii": False},
    )
    return _protect_restricted_response(response, resource)


@login_required
@require_POST
def resource_feedback(request, slug):
    resource = _resource_with_visible_mirrors(request, slug)
    issue_type = request.POST.get("issue_type", "")
    if issue_type not in ResourceIssue.IssueType.values:
        messages.error(request, "请选择有效的问题类型。")
        return redirect(resource.get_absolute_url())
    mirror = None
    mirror_id = request.POST.get("mirror", "").strip()
    if mirror_id:
        mirror = get_object_or_404(
            ResourceMirror,
            pk=mirror_id,
            resource=resource,
            status=ResourceMirror.Status.ACTIVE,
        )
    issue = ResourceIssue(
        resource=resource,
        mirror=mirror,
        reporter=request.user,
        issue_type=issue_type,
        details=request.POST.get("details", "").strip()[:1500],
    )
    issue.full_clean()
    issue.save()
    messages.success(request, "已收到反馈，我会在后台核对这个入口。")
    return redirect(resource.get_absolute_url())
