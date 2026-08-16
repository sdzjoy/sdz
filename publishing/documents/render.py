import html
import re
from typing import Any
from urllib.parse import urlsplit

import nh3

from .schema import ValidatedDocument, validate_document

ALLOWED_LINK_SCHEMES = {"http", "https", "mailto"}
ALLOWED_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "div",
    "h2",
    "h3",
    "hr",
    "li",
    "ol",
    "p",
    "pre",
    "s",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "u",
    "ul",
    "em",
}
ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
    "code": {"class"},
    "div": {"class", "data-node-type"},
    "ol": {"start"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
}
SAFE_LANGUAGE_PATTERN = re.compile(r"^[A-Za-z0-9_+.#-]{1,40}$")


def _safe_link(value: str) -> bool:
    if value.startswith(("/", "#")) and not value.startswith("//"):
        return True
    try:
        return urlsplit(value).scheme.lower() in ALLOWED_LINK_SCHEMES
    except ValueError:
        return False


def _render_marks(value: str, marks: list[dict[str, Any]]) -> str:
    rendered = value
    for mark in marks:
        mark_type = mark.get("type")
        if mark_type == "bold":
            rendered = f"<strong>{rendered}</strong>"
        elif mark_type == "italic":
            rendered = f"<em>{rendered}</em>"
        elif mark_type == "strike":
            rendered = f"<s>{rendered}</s>"
        elif mark_type == "underline":
            rendered = f"<u>{rendered}</u>"
        elif mark_type == "code":
            rendered = f"<code>{rendered}</code>"
        elif mark_type == "link":
            attrs = mark.get("attrs", {})
            href = attrs.get("href", "")
            if _safe_link(href):
                title = attrs.get("title")
                title_html = f' title="{html.escape(title, quote=True)}"' if title else ""
                rendered = (
                    f'<a href="{html.escape(href, quote=True)}"{title_html} '
                    f'rel="noopener noreferrer">{rendered}</a>'
                )
    return rendered


def _render_children(node: dict[str, Any]) -> str:
    return "".join(_render_node(child) for child in node.get("content", []))


def _span_attributes(attrs: dict[str, Any]) -> str:
    result = []
    for name in ("colspan", "rowspan"):
        value = attrs.get(name, 1)
        if value != 1:
            result.append(f' {name}="{value}"')
    return "".join(result)


def _render_node(node: dict[str, Any]) -> str:
    node_type = node["type"]
    attrs = node.get("attrs", {})
    children = _render_children(node)

    if node_type == "doc":
        return children
    if node_type == "text":
        escaped = html.escape(node.get("text", ""))
        return _render_marks(escaped, node.get("marks", []))
    if node_type == "paragraph":
        return f"<p>{children}</p>"
    if node_type == "heading":
        level = attrs.get("level", 2)
        return f"<h{level}>{children}</h{level}>"
    if node_type == "hardBreak":
        return "<br>"
    if node_type == "horizontalRule":
        return "<hr>"
    if node_type == "bulletList":
        return f"<ul>{children}</ul>"
    if node_type == "orderedList":
        start = attrs.get("start", 1)
        start_html = f' start="{start}"' if start != 1 else ""
        return f"<ol{start_html}>{children}</ol>"
    if node_type == "listItem":
        return f"<li>{children}</li>"
    if node_type == "blockquote":
        return f"<blockquote>{children}</blockquote>"
    if node_type == "codeBlock":
        language = attrs.get("language")
        language_html = (
            f' class="language-{html.escape(language, quote=True)}"'
            if isinstance(language, str) and SAFE_LANGUAGE_PATTERN.fullmatch(language)
            else ""
        )
        plain_code = "".join(
            html.escape(child.get("text", ""))
            for child in node.get("content", [])
            if child.get("type") == "text"
        )
        return f"<pre><code{language_html}>{plain_code}</code></pre>"
    if node_type == "table":
        return f"<table><tbody>{children}</tbody></table>"
    if node_type == "tableRow":
        return f"<tr>{children}</tr>"
    if node_type == "tableHeader":
        return f"<th{_span_attributes(attrs)}>{children}</th>"
    if node_type == "tableCell":
        return f"<td{_span_attributes(attrs)}>{children}</td>"

    node_name = html.escape(node_type, quote=True)
    return (
        f'<div class="content-unsupported-node" data-node-type="{node_name}">'
        f'<p>暂不支持的内容块：{html.escape(node_type)}</p>{children}</div>'
    )


def render_document(value: Any | ValidatedDocument) -> str:
    validated = value if isinstance(value, ValidatedDocument) else validate_document(value)
    rendered = _render_node(validated.doc)
    return nh3.clean(
        rendered,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_LINK_SCHEMES,
        link_rel="noopener noreferrer",
    )
