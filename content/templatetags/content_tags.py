from dataclasses import dataclass

import nh3
from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from latex2mathml import converter as latex_converter
from markdown_it import MarkdownIt

register = template.Library()
markdown = MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": False})

ALLOWED_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "em",
    "h2",
    "h3",
    "h4",
    "hr",
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "ul",
}

MAX_LATEX_LENGTH = 10_000


@dataclass(frozen=True)
class LatexRenderResult:
    html: str
    error: str | None = None


@register.filter
def safe_markdown(value):
    rendered = markdown.render(value or "")
    cleaned = nh3.clean(
        rendered,
        tags=ALLOWED_TAGS,
        attributes={"a": {"href", "title"}},
        url_schemes={"http", "https", "mailto"},
        link_rel="noopener noreferrer",
    )
    return mark_safe(cleaned)  # noqa: S308


def _formula_fallback(source, message):
    return format_html(
        '<span class="equation-error" role="note"><span>{}</span><code>{}</code></span>',
        message,
        source,
    )


@register.filter
def render_latex_mathml(value):
    """Convert LaTeX to local MathML while preserving invalid source safely."""
    return render_latex_mathml_result(value).html


def render_latex_mathml_result(value):
    source = str(value or "").strip()
    if not source:
        message = "公式内容为空"
        return LatexRenderResult(_formula_fallback(source, message), message)
    if len(source) > MAX_LATEX_LENGTH:
        message = "公式过长，暂时无法渲染"
        return LatexRenderResult(_formula_fallback(source, message), message)

    try:
        mathml = latex_converter.convert(source, display="block")
    except Exception:  # noqa: BLE001
        # Parser exception types vary with malformed input; no formula error should
        # make the whole article fail to render.
        message = "公式暂时无法渲染，已保留 LaTeX 源码"
        return LatexRenderResult(_formula_fallback(source, message), message)

    # Keep a defensive boundary if a future dependency changes its MathML-only contract.
    lowered = mathml.lower()
    if not lowered.startswith("<math ") or any(
        marker in lowered for marker in ("<script", "javascript:", " onerror=", " onload=")
    ):
        message = "公式输出未通过安全检查，已保留 LaTeX 源码"
        return LatexRenderResult(_formula_fallback(source, message), message)
    return LatexRenderResult(mark_safe(mathml))  # noqa: S308
