from types import SimpleNamespace

from django.http import Http404
from django.shortcuts import render
from django.utils.cache import patch_vary_headers

from publishing.documents import render_document, validate_document
from publishing.models import ContentEntry, SiteProfile
from publishing.public import PublishedContent, as_published

PUBLIC_CACHE_SECONDS = 60
KIND_CONFIG = {
    ContentEntry.Kind.ARTICLE: {
        "collection": "articles",
        "template": "content/article_page.html",
        "intro_field": "article_intro",
    },
    ContentEntry.Kind.PROJECT: {
        "collection": "projects",
        "template": "content/project_page.html",
        "intro_field": "project_intro",
    },
    ContentEntry.Kind.NOTE: {
        "collection": "notes",
        "template": "content/note_page.html",
        "intro_field": "note_intro",
    },
    ContentEntry.Kind.TOOL: {
        "collection": "tools",
        "template": "content/tool_page.html",
        "intro_field": "tool_intro",
    },
}


def _profile():
    return SiteProfile.objects.first() or SiteProfile()


def _public_queryset():
    return (
        ContentEntry.objects.published()
        .select_related("published_cover_asset")
        .prefetch_related("published_topics")
    )


def _public_render(request, template, context):
    response = render(request, template, context)
    patch_vary_headers(response, ("Cookie",))
    if request.user.is_authenticated:
        response["Cache-Control"] = "private, no-store"
    else:
        response["Cache-Control"] = f"public, max-age={PUBLIC_CACHE_SECONDS}"
    return response


def home(request):
    queryset = _public_queryset()
    projects = list(queryset.filter(kind=ContentEntry.Kind.PROJECT))
    current_projects = []
    completed_projects = []
    for project in as_published(projects, user=request.user):
        if project.status in {"active", "maintained"}:
            current_projects.append(project)
        elif project.status == "complete":
            completed_projects.append(project)
    latest_articles = as_published(
        queryset.filter(kind=ContentEntry.Kind.ARTICLE).order_by("-published_at")[:6],
        user=request.user,
    )
    latest_notes = as_published(
        queryset.filter(kind=ContentEntry.Kind.NOTE).order_by("-published_at")[:6],
        user=request.user,
    )
    featured_tools = as_published(
        queryset.filter(
            kind=ContentEntry.Kind.TOOL,
            published_featured=True,
        ).order_by("-published_at")[:4],
        user=request.user,
    )
    context = {
        "page": SimpleNamespace(title="少惰主 · SDZJOY"),
        "current_projects": current_projects[:4],
        "completed_projects": completed_projects[:4],
        "latest_articles": latest_articles,
        "latest_notes": latest_notes,
        "featured_tools": featured_tools,
        "has_public_content": bool(projects or latest_articles or latest_notes or featured_tools),
    }
    return _public_render(request, "core/home_page.html", context)


def content_index(request, kind):
    config = KIND_CONFIG.get(kind)
    if config is None:
        raise Http404
    profile = _profile()
    entries = _public_queryset().filter(kind=kind).order_by("-published_at", "-pk")
    page = SimpleNamespace(
        title=dict(ContentEntry.Kind.choices)[kind],
        intro=getattr(profile, config["intro_field"]),
    )
    context = {
        "page": page,
        config["collection"]: as_published(entries, user=request.user),
    }
    return _public_render(
        request,
        f"content/{kind}_index_page.html",
        context,
    )


def content_detail(request, kind, slug):
    config = KIND_CONFIG.get(kind)
    if config is None:
        raise Http404
    entry = _public_queryset().filter(kind=kind, published_slug=slug).first()
    if entry is None:
        raise Http404
    page = PublishedContent(entry, user=request.user)
    context = {
        "page": page,
        "breadcrumbs": (
            ("首页", "/"),
            (dict(ContentEntry.Kind.choices)[kind], f"/{config['collection']}/"),
            (page.title, ""),
        ),
    }
    return _public_render(request, config["template"], context)


def about(request):
    profile = _profile()
    context = {
        "page": SimpleNamespace(
            title="关于",
            intro=profile.about_intro,
            body_html=render_document(
                validate_document(profile.about_body_json),
                user=request.user,
            ),
        ),
        "breadcrumbs": (("首页", "/"), ("关于", "")),
    }
    return _public_render(request, "content/about_page.html", context)
