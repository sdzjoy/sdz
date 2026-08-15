from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from wagtail.signals import page_published, page_unpublished

from content.models import ArticlePage, NotePage, ProjectPage, ToolPage
from resources.models import Resource
from standards.models import Standard

from .models import SearchDocument
from .services import index_page, index_resource, index_standard


@receiver(post_save, sender=Standard)
def update_standard_document(sender, instance, **kwargs):
    index_standard(instance)


@receiver(post_delete, sender=Standard)
def delete_standard_document(sender, instance, **kwargs):
    SearchDocument.objects.filter(kind="standard", object_id=str(instance.pk)).delete()


@receiver(post_save, sender=Resource)
def update_resource_document(sender, instance, **kwargs):
    index_resource(instance)


@receiver(post_delete, sender=Resource)
def delete_resource_document(sender, instance, **kwargs):
    SearchDocument.objects.filter(kind="resource", object_id=str(instance.pk)).delete()


@receiver(page_published)
def update_page_document(sender, instance, **kwargs):
    page = instance.specific
    index_page(page)
    from notifications.models import Event
    from notifications.services import emit_event

    kind = next(
        (
            value
            for model, value in (
                (ProjectPage, "project"),
                (ArticlePage, "article"),
                (NotePage, "note"),
                (ToolPage, "tool"),
            )
            if isinstance(page, model)
        ),
        None,
    )
    if kind:
        emit_event(
            event_type=Event.EventType.CONTENT_PUBLISHED,
            title=f"{page.title} 已发布",
            payload={
                "item_type": kind,
                "object_id": page.pk,
                "summary": getattr(page, "summary", ""),
                "url": page.url,
            },
            dedupe_key=f"page-publication:{page.pk}:{page.latest_revision_id}",
            priority=Event.Priority.DIGEST,
        )


@receiver(page_unpublished)
def delete_page_document(sender, instance, **kwargs):
    index_page(instance.specific)
