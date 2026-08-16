from django.urls import path

from .api.articles import (
    autosave_article,
    create_article,
    publish_article,
    save_article,
)
from .views.content import (
    bulk_content_action,
    content_list,
    permanently_delete_content,
    restore_trashed_content,
)
from .views.dashboard import dashboard, placeholder
from .views.editor import article_create, article_edit, article_preview

app_name = "studio"

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("content/", content_list, name="content_list"),
    path("content/actions/", bulk_content_action, name="content_bulk_action"),
    path(
        "content/<int:pk>/restore/",
        restore_trashed_content,
        name="content_restore",
    ),
    path(
        "content/<int:pk>/delete-permanently/",
        permanently_delete_content,
        name="content_permanent_delete",
    ),
    path(
        "content/articles/new/",
        article_create,
        name="article_create",
    ),
    path(
        "content/articles/<int:pk>/",
        article_edit,
        name="article_edit",
    ),
    path(
        "content/articles/<int:pk>/preview/",
        article_preview,
        name="article_preview",
    ),
    path("api/articles/", create_article, name="api_article_create"),
    path(
        "api/articles/<int:pk>/autosave/",
        autosave_article,
        name="api_article_autosave",
    ),
    path("api/articles/<int:pk>/save/", save_article, name="api_article_save"),
    path(
        "api/articles/<int:pk>/publish/",
        publish_article,
        name="api_article_publish",
    ),
    path("assets/", placeholder, {"section": "assets"}, name="assets"),
    path("resources/", placeholder, {"section": "resources"}, name="resources"),
    path("users/", placeholder, {"section": "users"}, name="users"),
    path("settings/", placeholder, {"section": "settings"}, name="settings"),
]
