import nh3
from django import template
from django.utils.safestring import mark_safe
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
