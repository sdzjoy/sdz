from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db import connection
from django.db.models import Max, Q

from publishing.models import ContentEntry, ContentRevision
from resources.models import Resource
from standards.models import Standard

from .models import SearchDocument

LEVEL_RANK = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}


def allowed_levels(user):
    if user is None or not user.is_authenticated or not user.is_active:
        return ["L0"]
    rank = LEVEL_RANK.get(user.membership_level, 0)
    return [level for level, required in LEVEL_RANK.items() if required <= rank]


def search_documents(query, user, *, limit_per_group=20):
    query = " ".join(query.split())[:160]
    if not query:
        return {}
    documents = SearchDocument.objects.filter(access_level__in=allowed_levels(user))
    if connection.vendor == "postgresql":
        vector = (
            SearchVector("title", weight="A")
            + SearchVector("summary", weight="B")
            + SearchVector("search_text", weight="C")
        )
        search_query = SearchQuery(query, search_type="websearch", config="simple")
        documents = (
            documents.annotate(rank=SearchRank(vector, search_query))
            .filter(rank__gt=0)
            .order_by("-rank", "title")
        )
    else:
        documents = documents.filter(
            Q(title__icontains=query)
            | Q(summary__icontains=query)
            | Q(search_text__icontains=query)
        ).order_by("title")

    grouped = {}
    for document in documents:
        items = grouped.setdefault(document.kind, [])
        if len(items) < limit_per_group:
            items.append(document)
    return grouped


def _content_values(content):
    public_lastmod = getattr(content, "public_lastmod", None)
    if public_lastmod is None:
        public_revision = (
            content.revisions.filter(action=ContentRevision.Action.PUBLISH)
            .order_by("-number", "-pk")
            .first()
        )
        public_lastmod = public_revision.created_at if public_revision else None
    return {
        "kind": content.kind,
        "object_id": str(content.pk),
        "title": content.published_title,
        "summary": content.published_summary,
        "search_text": " ".join(
            filter(
                None,
                (
                    content.published_body_text,
                    " ".join(topic.name for topic in content.published_topics.all()),
                ),
            )
        ),
        "url": content.get_absolute_url(),
        "access_level": "L0",
        "source_updated_at": public_lastmod or content.published_at,
    }


def remove_content_document(content):
    SearchDocument.objects.filter(kind=content.kind, object_id=str(content.pk)).delete()


def index_content(content):
    if (
        content.deleted_at is not None
        or content.status != ContentEntry.Status.PUBLISHED
        or not content.published_slug
        or content.published_body_json is None
    ):
        remove_content_document(content)
        return
    values = _content_values(content)
    SearchDocument.objects.update_or_create(
        kind=content.kind,
        object_id=str(content.pk),
        defaults={key: value for key, value in values.items() if key not in {"kind", "object_id"}},
    )


def index_standard(standard):
    SearchDocument.objects.update_or_create(
        kind=SearchDocument.Kind.STANDARD,
        object_id=str(standard.pk),
        defaults={
            "title": f"{standard.code} {standard.title_cn}",
            "summary": standard.summary,
            "search_text": " ".join(
                filter(None, (standard.title_en, standard.ics_code, standard.ccs_code))
            ),
            "url": standard.get_absolute_url(),
            "access_level": "L0",
            "source_updated_at": standard.updated_at,
        },
    )


def index_resource(resource):
    if resource.status != Resource.Status.PUBLISHED:
        SearchDocument.objects.filter(
            kind=SearchDocument.Kind.RESOURCE, object_id=str(resource.pk)
        ).delete()
        return
    SearchDocument.objects.update_or_create(
        kind=SearchDocument.Kind.RESOURCE,
        object_id=str(resource.pk),
        defaults={
            "title": resource.title,
            "summary": resource.summary,
            # Deliberately exclude mirror URLs, access codes and checksum values.
            "search_text": " ".join(
                filter(None, (resource.author, resource.source_name, resource.file_format))
            ),
            "url": resource.get_absolute_url(),
            "access_level": resource.access_level,
            "source_updated_at": resource.updated_at,
        },
    )


def rebuild_index():
    expected = set()
    contents = (
        ContentEntry.objects.published()
        .prefetch_related("published_topics")
        .annotate(
            public_lastmod=Max(
                "revisions__created_at",
                filter=Q(revisions__action=ContentRevision.Action.PUBLISH),
            )
        )
    )
    for content in contents:
        index_content(content)
        expected.add((content.kind, str(content.pk)))
    for standard in Standard.objects.all():
        index_standard(standard)
        expected.add((SearchDocument.Kind.STANDARD, str(standard.pk)))
    for resource in Resource.objects.filter(status=Resource.Status.PUBLISHED):
        index_resource(resource)
        expected.add((SearchDocument.Kind.RESOURCE, str(resource.pk)))
    for document in SearchDocument.objects.all().only("pk", "kind", "object_id"):
        if (document.kind, document.object_id) not in expected:
            document.delete()
    return len(expected)
