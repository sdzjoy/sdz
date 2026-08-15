from content.models import ArticlePage, NotePage, ProjectPage, ToolPage
from resources.models import Resource
from standards.models import Standard

from .models import ContentReference


def resolve_reference(item_type, object_id, user):
    models = {
        ContentReference.PROJECT: ProjectPage,
        ContentReference.ARTICLE: ArticlePage,
        ContentReference.NOTE: NotePage,
        ContentReference.TOOL: ToolPage,
    }
    if item_type in models:
        page = models[item_type].objects.live().public().filter(pk=object_id).first()
        if page:
            return {"title": page.title, "url": page.url, "object": page}
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

