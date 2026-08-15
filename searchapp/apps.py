from django.apps import AppConfig


class SearchappConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "searchapp"
    verbose_name = "统一搜索"

    def ready(self):
        from . import signals  # noqa: F401

