from studio.models import AuditEvent


def record_content_event(*, actor, action, content, reason="", metadata=None):
    return AuditEvent.objects.create(
        actor=actor,
        action=action,
        object_type=content.kind,
        object_id=str(content.pk),
        object_label=content.title,
        reason=reason,
        metadata=metadata or {},
    )
