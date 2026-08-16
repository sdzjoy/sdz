from django.db import transaction
from django.utils import timezone

from publishing.models import Asset
from publishing.uploads import create_image_asset, find_asset_references
from studio.models import AuditEvent


def _record_asset_event(*, actor, action, asset):
    return AuditEvent.objects.create(
        actor=actor,
        action=action,
        object_type="asset",
        object_id=str(asset.pk),
        object_label=asset.title or asset.original_name,
        metadata={"kind": asset.kind, "mime_type": asset.mime_type},
    )


def upload_image_asset(uploaded, *, actor):
    return create_image_asset(
        uploaded,
        uploaded_by=actor,
        after_save=lambda asset: _record_asset_event(
            actor=actor,
            action=AuditEvent.Action.ASSET_UPLOAD,
            asset=asset,
        ),
    )


@transaction.atomic
def soft_delete_asset(asset, *, actor):
    locked = Asset.objects.select_for_update().get(pk=asset.pk, deleted_at__isnull=True)
    references = find_asset_references(locked)
    if references:
        return None, references
    locked.deleted_at = timezone.now()
    locked.save(update_fields={"deleted_at", "updated_at"})
    _record_asset_event(
        actor=actor,
        action=AuditEvent.Action.ASSET_DELETE,
        asset=locked,
    )
    return locked, []
