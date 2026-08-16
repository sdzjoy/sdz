from django.urls import path

from publishing.models import ContentEntry

from .views import about, content_detail, content_index, home

app_name = "publishing"

urlpatterns = [
    path("", home, name="home"),
    path(
        "articles/",
        content_index,
        {"kind": ContentEntry.Kind.ARTICLE},
        name="article_index",
    ),
    path(
        "articles/<str:slug>/",
        content_detail,
        {"kind": ContentEntry.Kind.ARTICLE},
        name="article_detail",
    ),
    path(
        "projects/",
        content_index,
        {"kind": ContentEntry.Kind.PROJECT},
        name="project_index",
    ),
    path(
        "projects/<str:slug>/",
        content_detail,
        {"kind": ContentEntry.Kind.PROJECT},
        name="project_detail",
    ),
    path(
        "notes/",
        content_index,
        {"kind": ContentEntry.Kind.NOTE},
        name="note_index",
    ),
    path(
        "notes/<str:slug>/",
        content_detail,
        {"kind": ContentEntry.Kind.NOTE},
        name="note_detail",
    ),
    path(
        "tools/",
        content_index,
        {"kind": ContentEntry.Kind.TOOL},
        name="tool_index",
    ),
    path(
        "tools/<str:slug>/",
        content_detail,
        {"kind": ContentEntry.Kind.TOOL},
        name="tool_detail",
    ),
    path("about/", about, name="about"),
]
