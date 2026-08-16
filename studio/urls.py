from django.urls import path

from .views.dashboard import dashboard, placeholder

app_name = "studio"

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("content/", placeholder, {"section": "content"}, name="content_list"),
    path(
        "content/articles/new/",
        placeholder,
        {"section": "article_create"},
        name="article_create",
    ),
    path("assets/", placeholder, {"section": "assets"}, name="assets"),
    path("resources/", placeholder, {"section": "resources"}, name="resources"),
    path("users/", placeholder, {"section": "users"}, name="users"),
    path("settings/", placeholder, {"section": "settings"}, name="settings"),
]
