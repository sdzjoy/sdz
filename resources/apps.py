from django.apps import AppConfig


class ResourcesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "resources"
    verbose_name = "资源目录"

    def ready(self):
        from . import signals  # noqa: F401
