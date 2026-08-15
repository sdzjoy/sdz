from django.urls import path

from . import views

urlpatterns = [
    path("", views.account_center, name="account_center"),
    path("export/", views.export_account_data, name="account_export"),
    path("delete/", views.request_account_deletion, name="account_delete_request"),
    path("deactivate/", views.deactivate_account, name="account_deactivate"),
]
