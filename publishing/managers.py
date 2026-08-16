from django.db import models
from django.utils import timezone


class ContentQuerySet(models.QuerySet):
    def active(self):
        return self.filter(deleted_at__isnull=True)

    def in_trash(self):
        return self.filter(deleted_at__isnull=False)

    def published(self):
        return self.active().filter(
            status="published",
            published_at__isnull=False,
            published_at__lte=timezone.now(),
        )

    def of_kind(self, kind):
        return self.filter(kind=kind)


class ContentManager(models.Manager.from_queryset(ContentQuerySet)):
    pass
