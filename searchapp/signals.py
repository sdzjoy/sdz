from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from notifications.models import Event
from notifications.services import emit_event
from publishing.events import (
    content_published,
    content_removed,
    content_restored,
    content_unpublished,
)
from publishing.models import ContentEntry
from resources.models import Resource
from standards.models import Standard

from .models import SearchDocument
from .services import (
    index_content,
    index_resource,
    index_standard,
    remove_content_document,
)


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


@receiver(content_published)
def update_content_document(sender, instance, **kwargs):
    index_content(instance)
    emit_event(
        event_type=Event.EventType.CONTENT_PUBLISHED,
        title=f"{instance.published_title} 已发布",
        payload={
            "item_type": instance.kind,
            "object_id": instance.pk,
            "summary": instance.published_summary,
            "url": instance.get_absolute_url(),
        },
        dedupe_key=f"content-publication:{instance.pk}:{instance.version}",
        priority=Event.Priority.DIGEST,
    )


@receiver(content_unpublished)
@receiver(content_removed)
def hide_content_document(sender, instance, **kwargs):
    remove_content_document(instance)


@receiver(content_restored)
def restore_content_document(sender, instance, **kwargs):
    index_content(instance)


@receiver(post_delete, sender=ContentEntry)
def delete_content_document(sender, instance, **kwargs):
    remove_content_document(instance)
