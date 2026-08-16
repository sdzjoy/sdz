import json
from uuid import uuid4

from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from publishing.models import Article, ContentEntry
from publishing.services import (
    ContentConflict,
    ContentStateError,
    autosave_draft,
    publish_content,
    save_draft,
)

from ..forms.articles import ArticlePayloadForm
from ..models import AuditEvent
from ..permissions import CONTENT_ROLES, studio_role_required
from ..services.audit import record_content_event

INTENTS = {"autosave", "save", "publish"}


def _read_payload(request):
    try:
        payload = json.loads(request.body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _error(message, *, code="invalid_request", status=400, **extra):
    return JsonResponse(
        {"ok": False, "code": code, "message": message, **extra},
        status=status,
    )


def _form_errors(form):
    return {
        name: [error["message"] for error in errors]
        for name, errors in form.errors.get_json_data().items()
    }


def _unique_slug(title, requested=""):
    base = slugify(requested or title, allow_unicode=True)[:140]
    if not base:
        base = f"draft-{uuid4().hex[:10]}"
    candidate = base
    suffix = 2
    while Article.objects.filter(slug=candidate).exists():
        candidate = f"{base[:150 - len(str(suffix))]}-{suffix}"
        suffix += 1
    return candidate


def _article_response(article, form, *, status=200):
    return JsonResponse(
        {
            "ok": True,
            "article": {
                "id": article.pk,
                "version": article.version,
                "status": article.status,
                "updated_at": article.updated_at.isoformat(),
                "edit_url": reverse("studio:article_edit", args=(article.pk,)),
                "preview_url": reverse("studio:article_preview", args=(article.pk,)),
                "autosave_url": reverse("studio:api_article_autosave", args=(article.pk,)),
                "save_url": reverse("studio:api_article_save", args=(article.pk,)),
                "publish_url": reverse("studio:api_article_publish", args=(article.pk,)),
                "public_url": article.get_absolute_url()
                if article.status == ContentEntry.Status.PUBLISHED
                else "",
            },
            "warnings": [
                {"code": warning.code, "message": warning.message, "path": warning.path}
                for warning in form.document_warnings
            ],
        },
        status=status,
    )


def _article_values(form, article=None):
    cleaned = form.cleaned_data
    title = cleaned["title"] or (article.title if article else "未命名文章")
    slug = cleaned["slug"] or (article.slug if article else _unique_slug(title))
    return {
        "title": title,
        "slug": slug,
        "summary": cleaned["summary"],
        "body_json": cleaned["body_json"],
        "featured": cleaned["featured"],
        "topic_ids": list(cleaned["topics"].values_list("pk", flat=True)),
        "extra_fields": {
            "published_on": cleaned["published_on"],
            "reading_minutes": cleaned["reading_minutes"],
            "parent_project_id": cleaned["parent_project"].pk
            if cleaned["parent_project"]
            else None,
        },
    }


def _intent_payload(request, intent):
    if intent not in INTENTS:
        return None, _error("不支持的保存方式。")
    payload = _read_payload(request)
    if payload is None:
        return None, _error("请求正文必须是 JSON 对象。")
    form = ArticlePayloadForm(payload, intent=intent)
    if not form.is_valid():
        return None, _error("正文或文章资料未通过检查。", fields=_form_errors(form))
    return form, None


@require_POST
@studio_role_required(*CONTENT_ROLES)
def create_article(request):
    payload = _read_payload(request)
    intent = payload.get("intent", "autosave") if payload else "autosave"
    form, error = _intent_payload(request, intent)
    if error:
        return error
    values = _article_values(form)
    try:
        with transaction.atomic():
            article = Article.objects.create(
                title=values["title"],
                slug=values["slug"],
                summary=values["summary"],
                body_json=values["body_json"],
                featured=values["featured"],
                author=request.user,
                **values["extra_fields"],
            )
            article.topics.set(values["topic_ids"])
            if intent == "publish":
                article = publish_content(
                    article,
                    expected_version=article.version,
                    actor=request.user,
                )
                audit_action = AuditEvent.Action.PUBLISH
            elif intent == "save":
                article = save_draft(
                    article,
                    expected_version=article.version,
                    actor=request.user,
                    **values,
                )
                audit_action = AuditEvent.Action.MANUAL_SAVE
            else:
                audit_action = None
            if audit_action:
                record_content_event(
                    actor=request.user,
                    action=audit_action,
                    content=article,
                )
    except IntegrityError:
        return _error("网址标识已被其他文章使用。", code="slug_conflict", status=409)
    return _article_response(article, form, status=201)


def _update_article(request, pk, intent):
    article = get_object_or_404(Article.objects.active(), pk=pk)
    form, error = _intent_payload(request, intent)
    if error:
        return error
    values = _article_values(form, article)
    expected_version = form.cleaned_data["version"]
    try:
        with transaction.atomic():
            if intent == "autosave":
                article = autosave_draft(
                    article,
                    expected_version=expected_version,
                    **values,
                )
            elif intent == "save":
                article = save_draft(
                    article,
                    expected_version=expected_version,
                    actor=request.user,
                    **values,
                )
                record_content_event(
                    actor=request.user,
                    action=AuditEvent.Action.MANUAL_SAVE,
                    content=article,
                )
            else:
                article = autosave_draft(
                    article,
                    expected_version=expected_version,
                    **values,
                )
                article = publish_content(
                    article,
                    expected_version=article.version,
                    actor=request.user,
                )
                record_content_event(
                    actor=request.user,
                    action=AuditEvent.Action.PUBLISH,
                    content=article,
                )
    except ContentConflict as conflict:
        return _error(
            "这篇文章已在其他窗口更新，当前内容没有被覆盖。",
            code="version_conflict",
            status=409,
            current_version=conflict.current_version,
        )
    except ContentStateError as state_error:
        return _error(str(state_error), code="invalid_state", status=409)
    except IntegrityError:
        return _error("网址标识已被其他文章使用。", code="slug_conflict", status=409)
    return _article_response(article, form)


@require_POST
@studio_role_required(*CONTENT_ROLES)
def autosave_article(request, pk):
    return _update_article(request, pk, "autosave")


@require_POST
@studio_role_required(*CONTENT_ROLES)
def save_article(request, pk):
    return _update_article(request, pk, "save")


@require_POST
@studio_role_required(*CONTENT_ROLES)
def publish_article(request, pk):
    return _update_article(request, pk, "publish")
