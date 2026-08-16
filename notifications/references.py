from publishing.models import ContentEntry
from publishing.public import PublishedContent
from resources.models import Resource
from standards.models import Standard

from .models import ContentReference


def resolve_reference(item_type, object_id, user):
    content_kinds = {
        ContentReference.PROJECT,
        ContentReference.ARTICLE,
        ContentReference.NOTE,
        ContentReference.TOOL,
    }
    if item_type in content_kinds:
        content = (
            ContentEntry.objects.published()
            .filter(pk=object_id, kind=item_type)
            .first()
        )
        if content:
            public = PublishedContent(content, user=user)
            return {"title": public.title, "url": public.url, "object": public}
        return None
    if item_type == ContentReference.STANDARD:
        item = Standard.objects.filter(pk=object_id).first()
    elif item_type == ContentReference.RESOURCE:
        item = Resource.objects.visible_to(user).filter(pk=object_id).first()
    else:
        return None
    if not item:
        return None
    title = item.title if item_type == ContentReference.RESOURCE else f"{item.code} {item.title_cn}"
    return {"title": title, "url": item.get_absolute_url(), "object": item}


def resolved_items(queryset, user):
    results = []
    for saved in queryset:
        reference = resolve_reference(saved.item_type, saved.object_id, user)
        if reference:
            results.append({"saved": saved, **reference})
    return results
