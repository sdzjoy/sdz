from django.templatetags.static import static
from django.utils.html import format_html
from wagtail import hooks
from wagtail.admin.ui.tables import Column
from wagtail.admin.viewsets.pages import PageListingViewSet

from .models import ArticlePage, NotePage, ProjectPage, ToolPage


@hooks.register("insert_global_admin_css")
def global_admin_css():
    return format_html('<link rel="stylesheet" href="{}">', static("css/admin.css"))


class ProjectListingViewSet(PageListingViewSet):
    model = ProjectPage
    icon = "folder-open-inverse"
    menu_label = "项目工作台"
    menu_order = 210
    add_to_admin_menu = True
    ordering = "-started_on"
    list_filter = ["status", "featured"]
    columns = PageListingViewSet.columns + [
        Column("status", label="状态", sort_key="status"),
        Column("started_on", label="开始日期", sort_key="started_on"),
    ]


class ArticleListingViewSet(PageListingViewSet):
    model = ArticlePage
    icon = "doc-full-inverse"
    menu_label = "文章工作台"
    menu_order = 220
    add_to_admin_menu = True
    ordering = "-published_on"
    list_filter = ["featured", "project"]
    columns = PageListingViewSet.columns + [
        Column("published_on", label="文章日期", sort_key="published_on"),
        Column("project", label="所属项目", sort_key="project__title"),
    ]


class NoteListingViewSet(PageListingViewSet):
    model = NotePage
    icon = "edit"
    menu_label = "随记工作台"
    menu_order = 230
    add_to_admin_menu = True
    ordering = "-noted_on"
    list_filter = ["project", "promoted_article"]
    columns = PageListingViewSet.columns + [
        Column("noted_on", label="记录日期", sort_key="noted_on"),
        Column("project", label="所属项目", sort_key="project__title"),
    ]


class ToolListingViewSet(PageListingViewSet):
    model = ToolPage
    icon = "cogs"
    menu_label = "工具工作台"
    menu_order = 240
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
