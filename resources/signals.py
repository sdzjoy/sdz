from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from notifications.models import Event
from notifications.services import emit_event

from .models import Resource, ResourceVersion


@receiver(m2m_changed, sender=Resource.taxonomies.through)
def notify_published_resource(sender, instance, action, **kwargs):
    if action != "post_add" or instance.status != Resource.Status.PUBLISHED:
        return
    emit_event(
        event_type=Event.EventType.CONTENT_PUBLISHED,
        title=f"新资源：{instance.title}",
        payload={
            "item_type": "resource",
            "object_id": instance.pk,
            "topic_ids": list(instance.taxonomies.values_list("pk", flat=True)),
            "summary": instance.summary,
            "url": instance.get_absolute_url(),
        },
        dedupe_key=f"resource-published:{instance.pk}",
        priority=Event.Priority.DIGEST,
    )


@receiver(post_save, sender=ResourceVersion)
def notify_resource_version(sender, instance, created, **kwargs):
    resource = instance.resource
    if not created or resource.status != Resource.Status.PUBLISHED:
        return
    emit_event(
        event_type=Event.EventType.RESOURCE_IMPORTANT,
        title=f"{resource.title} 发布了 {instance.version}",
        payload={
            "item_type": "resource",
            "object_id": resource.pk,
            "topic_ids": list(resource.taxonomies.values_list("pk", flat=True)),
            "summary": instance.change_notes,
            "url": resource.get_absolute_url(),
        },
        dedupe_key=f"resource-version:{instance.pk}",
    )
