from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from .models import Manual, ReferenceBook, Standard, TaxonomyTerm
from .services import build_coverage_matrix


def standard_list(request):
    standards = Standard.objects.prefetch_related("taxonomies")
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    category = request.GET.get("category", "").strip()
    jurisdiction = request.GET.get("jurisdiction", "").strip()
    taxonomy = request.GET.get("taxonomy", "").strip()

    if query:
        standards = standards.filter(
            Q(code__icontains=query)
            | Q(title_cn__icontains=query)
            | Q(title_en__icontains=query)
            | Q(ics_code__icontains=query)
            | Q(ccs_code__icontains=query)
        )
    if status in Standard.Status.values:
        standards = standards.filter(status=status)
    if category in Standard.Category.values:
        standards = standards.filter(category=category)
    if jurisdiction in Standard.Jurisdiction.values:
        standards = standards.filter(jurisdiction=jurisdiction)
    if taxonomy:
        standards = standards.filter(taxonomies__slug=taxonomy)

    page = Paginator(standards.distinct(), 24).get_page(request.GET.get("page"))
    context = {
        "page_obj": page,
        "filters": {
            "q": query,
            "status": status,
            "category": category,
            "jurisdiction": jurisdiction,
            "taxonomy": taxonomy,
        },
        "status_choices": Standard.Status.choices,
        "category_choices": Standard.Category.choices,
        "jurisdiction_choices": Standard.Jurisdiction.choices,
        "taxonomies": TaxonomyTerm.objects.all(),
    }
    return render(request, "standards/standard_list.html", context)


def standard_detail(request, slug):
    standard = get_object_or_404(
        Standard.objects.prefetch_related(
            "taxonomies",
            "standardorganization_set__organization",
            "evidence",
            "outgoing_relations__target",
            "incoming_relations__source",
            "status_history__evidence",
            "related_articles",
            "related_tools",
        ),
        slug=slug,
    )
    return render(request, "standards/standard_detail.html", {"standard": standard})


def coverage_matrix(request):
    return render(
        request,
        "standards/coverage_matrix.html",
        {"matrix": build_coverage_matrix()},
    )


def publication_list(request):
    query = request.GET.get("q", "").strip()
    manuals = Manual.objects.prefetch_related("taxonomies")
    books = ReferenceBook.objects.prefetch_related("taxonomies")
    if query:
        publication_filter = (
            Q(title__icontains=query)
            | Q(subtitle__icontains=query)
            | Q(authors__icontains=query)
            | Q(isbn__icontains=query)
        )
        manuals = manuals.filter(publication_filter)
        books = books.filter(publication_filter)
    return render(
        request,
        "standards/publication_list.html",
        {"manuals": manuals, "books": books, "query": query},
    )


def manual_detail(request, slug):
    manual = get_object_or_404(
        Manual.objects.prefetch_related("taxonomies", "related_standards"),
        slug=slug,
    )
    return render(
        request,
        "standards/publication_detail.html",
        {"publication": manual, "publication_type": "技术手册"},
    )


def book_detail(request, slug):
    book = get_object_or_404(
        ReferenceBook.objects.prefetch_related("taxonomies", "related_standards"),
        slug=slug,
    )
    return render(
        request,
        "standards/publication_detail.html",
        {"publication": book, "publication_type": "参考书"},
    )
