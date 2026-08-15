from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("notifications/", views.inbox, name="inbox"),
    path("notifications/preferences/", views.preferences, name="preferences"),
    path("notifications/<int:notification_id>/read/", views.mark_read, name="mark_read"),
    path("saved/", views.saved_items, name="saved_items"),
    path("saved/<str:mode>/toggle/", views.toggle_item, name="toggle_item"),
    path("saved/topic/<int:taxonomy_id>/toggle/", views.toggle_topic, name="toggle_topic"),
]

