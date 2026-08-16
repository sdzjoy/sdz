from django.db.models import Q
from django.urls import reverse
from wagtail.admin.ui.components import Component
from wagtail.documents import get_document_model
from wagtail.documents.permissions import permission_policy as document_permission_policy
from wagtail.images import get_image_model
from wagtail.images.permissions import permission_policy as image_permission_policy
from wagtail.permissions import page_permission_policy

from .models import (
    ArticleIndexPage,
    ArticlePage,
    NoteIndexPage,
    NotePage,
    ProjectPage,
    ToolPage,
)


class EditorialWorkbenchPanel(Component):
    name = "editorial_workbench"
    template_name = "wagtailadmin/home/editorial_workbench.html"
    order = 10

    @staticmethod
    def _permitted_page_ids(user):
        return page_permission_policy.instances_user_has_any_permission_for(
            user, {"change", "publish"}
        ).values_list("pk", flat=True)

    @staticmethod
    def _add_url(user, parent_model, listing_namespace):
        parent = parent_model.objects.first()
        if parent and page_permission_policy.user_has_permission_for_instance(
            user, "add", parent
        ):
            return reverse(f"{listing_namespace}:choose_parent")
        return ""

    @staticmethod
    def _asset_count(user, model, permission_policy):
        if user.is_superuser:
            return model.objects.count()
        return permission_policy.instances_user_has_any_permission_for(
            user, {"change", "choose"}
        ).count()

    @staticmethod
    def _quick_links(user):
        links = []
        if page_permission_policy.user_has_any_permission(
            user, {"add", "change", "publish"}
        ):
            links.extend(
                [
                    {"label": "全部文章", "url": reverse("article_pages:index")},
                    {"label": "全部随记", "url": reverse("note_pages:index")},
                    {"label": "项目", "url": reverse("project_pages:index")},
                    {"label": "工具", "url": reverse("tool_pages:index")},
                ]
            )
        if user.has_perm("content.view_topic"):
            links.append(
                {"label": "主题", "url": reverse("wagtailsnippets_content_topic:list")}
            )
        if image_permission_policy.user_has_any_permission(
            user, {"add", "change", "choose"}
        ):
            links.append({"label": "图片库", "url": reverse("wagtailimages:index")})
        if document_permission_policy.user_has_any_permission(
            user, {"add", "change", "choose"}
        ):
            links.append({"label": "文件库", "url": reverse("wagtaildocs:index")})
        links.append({"label": "查看主站", "url": "/", "external": True})
        return links

    def get_context_data(self, parent_context):
        context = super().get_context_data(parent_context)
        request = parent_context["request"]
        permitted_ids = self._permitted_page_ids(request.user)

        articles = ArticlePage.objects.filter(pk__in=permitted_ids)
        notes = NotePage.objects.filter(pk__in=permitted_ids)
        projects = ProjectPage.objects.filter(pk__in=permitted_ids)
        tools = ToolPage.objects.filter(pk__in=permitted_ids)
        can_manage_pages = page_permission_policy.user_has_any_permission(
            request.user, {"add", "change", "publish"}
        )

        context.update(
            {
                "request": request,
                "can_manage_pages": can_manage_pages,
                "create_article_url": self._add_url(
                    request.user, ArticleIndexPage, "article_pages"
                ),
                "create_note_url": self._add_url(
                    request.user, NoteIndexPage, "note_pages"
                ),
                "recent_drafts": articles.filter(
                    Q(live=False) | Q(has_unpublished_changes=True)
                ).order_by("-latest_revision_created_at")[:5],
                "recent_published": articles.filter(live=True).order_by(
                    "-last_published_at", "-pk"
                )[:5],
                "pending_notes": notes.filter(promoted_article__isnull=True).order_by(
                    "-noted_on", "-pk"
                )[:5],
                "stats": [
                    {"label": "文章", "count": articles.count()},
                    {"label": "随记", "count": notes.count()},
                    {"label": "项目", "count": projects.count()},
                    {"label": "工具", "count": tools.count()},
                    {
                        "label": "图片",
                        "count": self._asset_count(
                            request.user, get_image_model(), image_permission_policy
                        ),
                    },
                    {
                        "label": "文件",
                        "count": self._asset_count(
                            request.user,
                            get_document_model(),
                            document_permission_policy,
                        ),
                    },
                ],
                "quick_links": self._quick_links(request.user),
            }
        )
        return context
