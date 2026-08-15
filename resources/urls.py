from django.urls import path

from . import views

app_name = "resources"

urlpatterns = [
    path("", views.resource_list, name="resource_list"),
    path("api/<slug:slug>/", views.resource_detail_json, name="resource_detail_json"),
    path("<slug:slug>/feedback/", views.resource_feedback, name="resource_feedback"),
    path("<slug:slug>/", views.resource_detail, name="resource_detail"),
]
