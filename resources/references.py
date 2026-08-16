from django.db.models import Prefetch

from resources.models import Resource, ResourceMirror


def resolve_resource_reference(resource_id, user):
    """Resolve an embeddable resource without bypassing publication or membership.

    Only active mirrors are attached, and an unauthorized caller receives ``None``
    rather than resource metadata that could reveal a restricted record.
    """

    active_mirrors = ResourceMirror.objects.filter(status=ResourceMirror.Status.ACTIVE)
    return (
        Resource.objects.visible_to(user)
        .prefetch_related(
            Prefetch("mirrors", queryset=active_mirrors, to_attr="active_mirrors")
        )
        .filter(pk=resource_id)
        .first()
    )
