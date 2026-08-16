from django.urls import path

from .views.content import (
    bulk_content_action,
    content_list,
    permanently_delete_content,
    restore_trashed_content,
)
from .views.dashboard import dashboard, placeholder

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
        placeholder,
        {"section": "article_create"},
        name="article_create",
    ),
    path(
        "content/articles/<int:pk>/",
        placeholder,
        {"section": "article_create"},
        name="article_edit",
    ),
    path("assets/", placeholder, {"section": "assets"}, name="assets"),
    path("resources/", placeholder, {"section": "resources"}, name="resources"),
    path("users/", placeholder, {"section": "users"}, name="users"),
    path("settings/", placeholder, {"section": "settings"}, name="settings"),
]
