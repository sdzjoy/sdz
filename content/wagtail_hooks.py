from django.templatetags.static import static
from django.urls import path, reverse
from django.utils.html import format_html
from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.admin.ui.tables import BooleanColumn, Column, DateColumn
from wagtail.admin.views.pages.listing import IndexView as PageIndexView
from wagtail.admin.viewsets.pages import PageListingViewSet
from wagtail.permissions import page_permission_policy

from .admin_views import math_preview
from .cms_components import EditorialWorkbenchPanel
from .models import ArticlePage, NotePage, ProjectPage, ToolPage


@hooks.register("insert_global_admin_css")
def global_admin_css():
    return format_html('<link rel="stylesheet" href="{}">', static("css/admin.css"))


@hooks.register("insert_editor_js")
def editorial_admin_js():
    return format_html(
        '<script src="{}" defer data-editorial-math-preview-url="{}"></script>',
        static("js/editorial-admin.js"),
        reverse("editorial_math_preview"),
    )


@hooks.register("register_admin_urls")
def register_editorial_admin_urls():
    return [
        path(
            "editorial/math-preview/",
            math_preview,
            name="editorial_math_preview",
        )
    ]


@hooks.register("construct_homepage_panels")
def construct_editorial_homepage(request, panels):
    panels[:] = [EditorialWorkbenchPanel()]


class EditorialArticleIndexView(PageIndexView):
    page_title = "文章"
    add_item_label = "新建文章"

    def get_base_queryset(self):
        return super().get_base_queryset().select_related("project").prefetch_related("topics")


class TopicsColumn(Column):
    def get_value(self, instance):
        return "、".join(topic.name for topic in instance.topics.all()) or "—"


class ReadingTimeColumn(Column):
    def get_value(self, instance):
        return f"{instance.effective_reading_minutes} 分钟"


class PageTypeMenuItem(MenuItem):
    page_model = None

    def is_shown(self, request):
        if request.user.is_superuser:
            return True
        permitted_ids = page_permission_policy.instances_user_has_any_permission_for(
            request.user,
            {"change", "publish", "bulk_delete", "lock", "unlock"},
        ).values_list("pk", flat=True)
        if self.page_model.objects.filter(pk__in=permitted_ids).exists():
            return True
        return any(
            page_permission_policy.user_has_permission_for_instance(
                request.user, "add", parent
            )
            for parent_model in self.page_model.allowed_parent_page_models()
            for parent in parent_model.objects.all()
        )


class PermissionAwarePageListingViewSet(PageListingViewSet):
    menu_item_class = PageTypeMenuItem

    def get_menu_item(self, order=None):
        item = super().get_menu_item(order=order)
        item.page_model = self.model
        return item


class ProjectListingViewSet(PermissionAwarePageListingViewSet):
    model = ProjectPage
    icon = "folder-open-inverse"
    menu_label = "项目"
    menu_order = 220
    add_to_admin_menu = True
    ordering = "-started_on"
    list_filter = ["status", "featured"]
    columns = PageListingViewSet.columns + [
        Column("status", label="状态", sort_key="status"),
        Column("started_on", label="开始日期", sort_key="started_on"),
    ]


class ArticleListingViewSet(PermissionAwarePageListingViewSet):
    model = ArticlePage
    index_view_class = EditorialArticleIndexView
    icon = "doc-full-inverse"
    menu_label = "文章"
    menu_order = 200
    add_to_admin_menu = True
    ordering = "-published_on"
    list_filter = [
        "live",
        "has_unpublished_changes",
        "project",
        "topics",
        "published_on",
        "featured",
    ]
    columns = PageListingViewSet.columns + [
        DateColumn("published_on", label="文章日期", sort_key="published_on"),
        Column("project", label="所属项目", sort_key="project__title"),
        TopicsColumn("topics", label="主题"),
        ReadingTimeColumn("reading_time", label="阅读时间"),
        BooleanColumn("featured", label="首页推荐", sort_key="featured"),
    ]


class NoteListingViewSet(PermissionAwarePageListingViewSet):
    model = NotePage
    icon = "edit"
    menu_label = "随记"
    menu_order = 210
    add_to_admin_menu = True
    ordering = "-noted_on"
    list_filter = ["project", "promoted_article"]
    columns = PageListingViewSet.columns + [
        Column("noted_on", label="记录日期", sort_key="noted_on"),
        Column("project", label="所属项目", sort_key="project__title"),
    ]


class ToolListingViewSet(PermissionAwarePageListingViewSet):
    model = ToolPage
    icon = "cogs"
    menu_label = "工具"
    menu_order = 230
    add_to_admin_menu = True
    ordering = "-launched_on"
    list_filter = ["status", "featured", "project"]
    columns = PageListingViewSet.columns + [
        Column("status", label="状态", sort_key="status"),
        Column("launched_on", label="上线日期", sort_key="launched_on"),
    ]


project_listing = ProjectListingViewSet("project_pages")
article_listing = ArticleListingViewSet("article_pages")
note_listing = NoteListingViewSet("note_pages")
tool_listing = ToolListingViewSet("tool_pages")


@hooks.register("register_admin_viewset")
def register_project_listing():
    return project_listing


@hooks.register("register_admin_viewset")
def register_article_listing():
    return article_listing


@hooks.register("register_admin_viewset")
def register_note_listing():
    return note_listing


@hooks.register("register_admin_viewset")
def register_tool_listing():
    return tool_listing
