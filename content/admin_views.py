from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .templatetags.content_tags import MAX_LATEX_LENGTH, render_latex_mathml_result


@require_POST
def math_preview(request):
    source = request.POST.get("latex", "")
    result = render_latex_mathml_result(source)
    status = 400 if not source.strip() or len(source) > MAX_LATEX_LENGTH else 200
    return JsonResponse(
        {
            "ok": result.error is None,
            "html": str(result.html),
            "error": result.error,
        },
        status=status,
    )
