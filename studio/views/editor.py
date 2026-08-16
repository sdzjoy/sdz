from datetime import date

from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from publishing.documents import CURRENT_SCHEMA_VERSION, empty_document
from publishing.models import Article, Project, Topic

from ..permissions import CONTENT_ROLES, studio_context, studio_role_required


def _editor_context(request, article=None):
    context = studio_context(request.user)
    context.update(
        {
            "studio_section": "content",
            "article": article,
            "projects": Project.objects.active().order_by("title"),
            "topics": Topic.objects.order_by("name"),
            "selected_topic_ids": set(article.topics.values_list("pk", flat=True))
            if article
            else set(),
            "editor_config": {
                "schemaVersion": CURRENT_SCHEMA_VERSION,
                "articleId": article.pk if article else None,
                "version": article.version if article else 0,
                "status": article.status if article else "draft",
                "title": article.title if article else "",
                "slug": article.slug if article else "",
                "summary": article.summary if article else "",
                "featured": article.featured if article else False,
                "publishedOn": (article.published_on if article else date.today()).isoformat(),
                "readingMinutes": article.reading_minutes if article else None,
                "parentProjectId": article.parent_project_id if article else None,
                "topicIds": list(article.topics.values_list("pk", flat=True))
                if article
                else [],
                "body": (article.body_json if article else empty_document())["doc"],
                "createUrl": reverse("studio:api_article_create"),
                "autosaveUrl": reverse("studio:api_article_autosave", args=(article.pk,))
                if article
                else "",
                "saveUrl": reverse("studio:api_article_save", args=(article.pk,))
                if article
                else "",
                "publishUrl": reverse("studio:api_article_publish", args=(article.pk,))
                if article
                else "",
                "previewUrl": reverse("studio:article_preview", args=(article.pk,))
                if article
                else "",
            },
        }
    )
    return context


@studio_role_required(*CONTENT_ROLES)
def article_create(request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    return render(request, "studio/editor/article.html", _editor_context(request))


@studio_role_required(*CONTENT_ROLES)
def article_edit(request, pk):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    article = get_object_or_404(Article.objects.active(), pk=pk)
    return render(request, "studio/editor/article.html", _editor_context(request, article))


@studio_role_required(*CONTENT_ROLES)
def article_preview(request, pk):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    article = get_object_or_404(
        Article.objects.active().prefetch_related("topics"),
        pk=pk,
    )
    context = studio_context(request.user)
    context.update({"studio_section": "content", "article": article})
    return render(request, "studio/editor/preview.html", context)
