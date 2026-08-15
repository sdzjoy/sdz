from django.db import DatabaseError
from django.shortcuts import render

from .services import search_documents


def search(request):
    query = request.GET.get("q", "").strip()[:160]
    degraded = False
    groups = {}
    if query:
        try:
            groups = search_documents(query, request.user)
        except DatabaseError:
            degraded = True
    return render(
        request,
        "searchapp/search.html",
        {"query": query, "groups": groups, "degraded": degraded},
    )

