from django.contrib import messages
from django.db import transaction
from django.http import HttpResponseBadRequest, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from publishing.documents import render_document, validate_document
from publishing.models import ContentEntry, ContentRevision
from publishing.services import ContentConflict, ContentStateError, restore_revision

from ..models import AuditEvent
from ..permissions import CONTENT_ROLES, studio_context, studio_role_required
from ..services.audit import record_content_event


def _revision_context(request, content, *, selected=None):
    revisions = content.revisions.select_related("created_by").all()
    context = studio_context(request.user)
    context.update(
        {
            "studio_section": "content",
            "content_item": content,
            "revisions": revisions,
            "selected_revision": selected,
        }
    )
    return context


@studio_role_required(*CONTENT_ROLES)
def revision_list(request, pk):
    content = get_object_or_404(ContentEntry.objects.active(), pk=pk)
    return render(
        request,
        "studio/revisions/list.html",
        _revision_context(request, content),
    )


@studio_role_required(*CONTENT_ROLES)
def revision_preview(request, pk, revision_pk):
    content = get_object_or_404(ContentEntry.objects.active(), pk=pk)
    revision = get_object_or_404(
        ContentRevision.objects.select_related("created_by"),
        pk=revision_pk,
        content=content,
    )
    snapshot = revision.snapshot
    common = snapshot.get("common", {})
    preview_document = validate_document(common.get("body_json"))
    context = _revision_context(request, content, selected=revision)
    context.update(
        {
            "snapshot_title": common.get("title", ""),
            "snapshot_summary": common.get("summary", ""),
            "preview_html": render_document(preview_document, user=request.user),
        }
    )
    return render(request, "studio/revisions/preview.html", context)


@studio_role_required(*CONTENT_ROLES)
def restore_content_revision(request, pk, revision_pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    content = get_object_or_404(ContentEntry.objects.active(), pk=pk)
    revision = get_object_or_404(ContentRevision, pk=revision_pk, content=content)
    try:
        expected_version = int(request.POST.get("version", ""))
    except (TypeError, ValueError):
        return HttpResponseBadRequest("缺少有效的当前版本号。")

    try:
        with transaction.atomic():
            restored = restore_revision(
                revision,
                expected_version=expected_version,
                actor=request.user,
                revision_summary=f"恢复到版本 {revision.number}",
            )
            record_content_event(
                actor=request.user,
                action=AuditEvent.Action.RESTORE_REVISION,
                content=restored,
                reason=f"恢复到版本 {revision.number}",
                metadata={"restored_revision": revision.number},
            )
    except ContentConflict as conflict:
        messages.error(request, "内容已在其他窗口更新，请确认最新版本后再恢复。")
        content.refresh_from_db()
        response = render(
            request,
            "studio/revisions/list.html",
            _revision_context(request, content),
            status=409,
        )
        response["X-Current-Content-Version"] = str(conflict.current_version)
        return response
    except ContentStateError as error:
        messages.error(request, str(error))
        return redirect(reverse("studio:revision_list", args=(content.pk,)))

    messages.success(request, f"已恢复《{restored.title}》的历史版本；恢复前状态也已保存。")
    return redirect(reverse("studio:revision_list", args=(restored.pk,)))
