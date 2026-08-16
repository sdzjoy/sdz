from datetime import timedelta

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import models, transaction
from django.db.models.deletion import ProtectedError
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from publishing.models import ContentEntry
from publishing.services import (
    ContentConflict,
    ContentStateError,
    move_to_trash,
    publish_content,
    restore_from_trash,
    unpublish_content,
)

from ..forms.content import BulkContentActionForm, ContentFilterForm, PermanentDeleteForm
from ..models import AuditEvent
from ..permissions import CONTENT_ROLES, OWNER_ROLES, studio_context, studio_role_required
from ..services.audit import record_content_event

PERMANENT_DELETE_DELAY = timedelta(days=30)


def _filtered_content(form):
    cleaned = form.cleaned_data
    queryset = ContentEntry.objects.all()
    if cleaned.get("location") == "trash":
        queryset = queryset.in_trash()
    else:
        queryset = queryset.active()
    if cleaned.get("kind"):
        queryset = queryset.of_kind(cleaned["kind"])
    if cleaned.get("status"):
        queryset = queryset.filter(status=cleaned["status"])
    if cleaned.get("topic"):
        queryset = queryset.filter(topics=cleaned["topic"])
    if cleaned.get("q"):
        queryset = queryset.filter(
            models.Q(title__icontains=cleaned["q"])
            | models.Q(summary__icontains=cleaned["q"])
        )
    if cleaned.get("date_from"):
        queryset = queryset.filter(updated_at__date__gte=cleaned["date_from"])
    if cleaned.get("date_to"):
        queryset = queryset.filter(updated_at__date__lte=cleaned["date_to"])
    return queryset.select_related("author", "deleted_by").prefetch_related("topics").distinct()


@studio_role_required(*CONTENT_ROLES)
def content_list(request):
    filter_form = ContentFilterForm(request.GET or None)
    if filter_form.is_valid():
        queryset = _filtered_content(filter_form)
    else:
        queryset = ContentEntry.objects.active().select_related("author").prefetch_related("topics")

    from django.core.paginator import Paginator

    page_obj = Paginator(queryset, 25).get_page(request.GET.get("page"))
    context = studio_context(request.user)
    context.update(
        {
            "studio_section": "content",
            "filter_form": filter_form,
            "page_obj": page_obj,
            "content_items": page_obj.object_list,
            "kind_choices": ContentEntry.Kind.choices,
            "active_kind": filter_form.cleaned_data.get("kind", "")
            if filter_form.is_valid()
            else "",
            "in_trash": filter_form.is_valid()
            and filter_form.cleaned_data.get("location") == "trash",
            "advanced_open": any(
                request.GET.get(name) for name in ("topic", "date_from", "date_to")
            ),
            "permanent_delete_before": timezone.now() - PERMANENT_DELETE_DELAY,
        }
    )
    return render(request, "studio/content/list.html", context)


@studio_role_required(*CONTENT_ROLES)
def bulk_content_action(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    allowed_ids = ContentEntry.objects.active().values_list("pk", flat=True)
    form = BulkContentActionForm(request.POST, allowed_ids=allowed_ids)
    if not form.is_valid():
        messages.error(request, "请选择内容和要执行的操作。")
        return redirect(reverse("studio:content_list"))

    action = form.cleaned_data["action"]
    items = list(ContentEntry.objects.filter(pk__in=form.cleaned_data["selected"]).active())
    succeeded = 0
    for item in items:
        try:
            with transaction.atomic():
                if action == "publish":
                    publish_content(item, expected_version=item.version, actor=request.user)
                    audit_action = AuditEvent.Action.BULK_PUBLISH
                elif action == "unpublish":
                    unpublish_content(item, expected_version=item.version, actor=request.user)
                    audit_action = AuditEvent.Action.BULK_UNPUBLISH
                else:
                    move_to_trash(item, expected_version=item.version, actor=request.user)
                    audit_action = AuditEvent.Action.MOVE_TO_TRASH
                record_content_event(actor=request.user, action=audit_action, content=item)
            succeeded += 1
        except (ContentConflict, ContentStateError) as error:
            messages.error(request, f"{item.title}：{error}")
    if succeeded:
        messages.success(request, f"已处理 {succeeded} 项内容。")
    return redirect(reverse("studio:content_list"))


@studio_role_required(*CONTENT_ROLES)
def restore_trashed_content(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    item = get_object_or_404(ContentEntry.objects.in_trash(), pk=pk)
    with transaction.atomic():
        restored = restore_from_trash(
            item,
            expected_version=item.version,
            actor=request.user,
        )
        record_content_event(
            actor=request.user,
            action=AuditEvent.Action.RESTORE_FROM_TRASH,
            content=restored,
        )
    messages.success(request, f"已恢复《{restored.title}》。")
    return redirect(f"{reverse('studio:content_list')}?location=trash")


@studio_role_required(*OWNER_ROLES)
def permanently_delete_content(request, pk):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    item = get_object_or_404(ContentEntry.objects.in_trash(), pk=pk)
    if item.deleted_at > timezone.now() - PERMANENT_DELETE_DELAY:
        raise PermissionDenied("内容进入回收站满 30 天后才能永久删除。")
    form = PermanentDeleteForm(request.POST)
    if not form.is_valid():
        messages.error(request, "永久删除必须填写至少 5 个字的原因。")
        return redirect(f"{reverse('studio:content_list')}?location=trash")

    object_id = item.pk
    object_kind = item.kind
    object_title = item.title
    try:
        with transaction.atomic():
            item.delete()
            AuditEvent.objects.create(
                actor=request.user,
                action=AuditEvent.Action.PERMANENT_DELETE,
                object_type=object_kind,
                object_id=str(object_id),
                object_label=object_title,
                reason=form.cleaned_data["reason"],
            )
    except ProtectedError as error:
        raise Http404("内容仍被其他记录引用，不能永久删除。") from error
    messages.success(request, f"已永久删除《{object_title}》。")
    return redirect(f"{reverse('studio:content_list')}?location=trash")
