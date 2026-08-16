from django.urls import path

from .api.articles import (
    autosave_article,
    create_article,
    publish_article,
    save_article,
)
from .api.assets import delete_image, upload_image
from .api.references import reference_search
from .views.assets import asset_library, delete_asset
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
    path("assets/", asset_library, name="assets"),
    path("assets/<int:pk>/delete/", delete_asset, name="asset_delete"),
    path("api/assets/images/", upload_image, name="api_asset_upload"),
    path("api/references/", reference_search, name="api_reference_search"),
    path(
        "api/assets/images/<int:pk>/delete/",
        delete_image,
        name="api_asset_delete",
    ),
    path("resources/", placeholder, {"section": "resources"}, name="resources"),
    path("users/", placeholder, {"section": "users"}, name="users"),
    path("settings/", placeholder, {"section": "settings"}, name="settings"),
]
