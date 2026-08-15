from django.urls import path

from . import views

app_name = "standards"

urlpatterns = [
    path("", views.standard_list, name="standard_list"),
    path("coverage/", views.coverage_matrix, name="coverage_matrix"),
    path("library/", views.publication_list, name="publication_list"),
    path("manuals/<slug:slug>/", views.manual_detail, name="manual_detail"),
    path("books/<slug:slug>/", views.book_detail, name="book_detail"),
    path("<slug:slug>/", views.standard_detail, name="standard_detail"),
]
