import html
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import nh3
from latex2mathml.converter import convert as latex_to_mathml

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
    "figure",
    "figcaption",
    "img",
    "aside",
    "dl",
    "dt",
    "dd",
    "span",
    "small",
    "math",
    "mrow",
    "mi",
    "mn",
    "mo",
    "mfrac",
    "msqrt",
    "mroot",
    "msup",
    "msub",
    "msubsup",
    "munder",
    "mover",
    "munderover",
    "mtable",
    "mtr",
    "mtd",
    "mtext",
    "mspace",
    "semantics",
    "annotation",
}
ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
    "code": {"class"},
    "div": {"class", "data-node-type"},
    "ol": {"start"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
    "img": {"src", "alt", "title", "width", "height", "loading", "decoding"},
    "aside": {"class"},
    "dl": {"class"},
    "dd": {"class"},
    "span": {"class"},
    "small": {"class"},
    "math": {"xmlns", "display", "aria-label"},
    "mo": {"fence", "separator", "stretchy", "form"},
    "mspace": {"width", "height", "depth", "linebreak"},
    "mtable": {"columnalign", "rowalign", "columnspacing", "rowspacing"},
    "mtd": {"columnspan", "rowspan"},
    "annotation": {"encoding"},
}
SAFE_LANGUAGE_PATTERN = re.compile(r"^[A-Za-z0-9_+.#-]{1,40}$")
MATH_TAGS = {tag for tag in ALLOWED_TAGS if tag.startswith("m")} | {
    "semantics",
    "annotation",
}
MATH_ATTRIBUTES = {
    key: value for key, value in ALLOWED_ATTRIBUTES.items() if key in MATH_TAGS
}


@dataclass
class RenderContext:
    user: Any = None
    standards: dict[int, Any] = field(default_factory=dict)
    resources: dict[int, Any] = field(default_factory=dict)


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


def _render_children(node: dict[str, Any], context: RenderContext) -> str:
    return "".join(_render_node(child, context) for child in node.get("content", []))


def _span_attributes(attrs: dict[str, Any]) -> str:
    result = []
    for name in ("colspan", "rowspan"):
        value = attrs.get(name, 1)
        if value != 1:
            result.append(f' {name}="{value}"')
    return "".join(result)


def _render_equation(latex: str) -> str:
    try:
        mathml = latex_to_mathml(latex)
        if len(mathml) > 100_000:
            raise ValueError("generated MathML is too large")
        safe_mathml = nh3.clean(
            mathml,
            tags=MATH_TAGS,
            attributes=MATH_ATTRIBUTES,
            strip_comments=True,
        )
        if "<math" not in safe_mathml:
            raise ValueError("MathML root was removed")
        return f'<div class="content-equation">{safe_mathml}</div>'
    except Exception:  # The original source remains in JSON for later correction.
        source = html.escape(latex)
        return (
            '<div class="content-equation content-equation-fallback">'
            f"<code>{source}</code><small>公式暂时无法渲染</small></div>"
        )


def _render_standard_reference(standard_id: int, context: RenderContext) -> str:
    if standard_id not in context.standards:
        from standards.models import Standard

        context.standards[standard_id] = Standard.objects.filter(pk=standard_id).first()
    standard = context.standards[standard_id]
    if standard is None:
        return (
            '<aside class="content-reference content-reference-missing">'
            f"<strong>规范记录 #{standard_id}</strong><small>当前不可用</small></aside>"
        )
    href = html.escape(standard.get_absolute_url(), quote=True)
    code = html.escape(standard.code)
    title = html.escape(standard.title_cn)
    status = html.escape(standard.get_status_display())
    return (
        '<aside class="content-reference">'
        f'<a href="{href}"><strong>{code}</strong><span>{title}</span></a>'
        f"<small>{status}</small></aside>"
    )


def _render_cloud_resource(resource_id: int, context: RenderContext) -> str:
    if resource_id not in context.resources:
        from resources.references import resolve_resource_reference

        context.resources[resource_id] = resolve_resource_reference(
            resource_id,
            context.user,
        )
    resource = context.resources[resource_id]
    if resource is None:
        return (
            '<aside class="content-cloud-resource content-cloud-resource-locked">'
            "<strong>受限网盘资源</strong>"
            "<p>登录或提升会员等级后查看资源入口。</p></aside>"
        )
    title = html.escape(resource.title)
    detail_url = html.escape(resource.get_absolute_url(), quote=True)
    mirrors = []
    for mirror in resource.active_mirrors:
        if not _safe_link(mirror.share_url):
            continue
        provider = html.escape(mirror.get_provider_display())
        share_url = html.escape(mirror.share_url, quote=True)
        code = (
            f"<code>提取码：{html.escape(mirror.extraction_code)}</code>"
            if mirror.extraction_code
            else ""
        )
        mirrors.append(
            f'<li><a href="{share_url}">{provider}</a>{code}</li>'
        )
    mirror_html = f"<ul>{''.join(mirrors)}</ul>" if mirrors else "<p>暂没有可用入口。</p>"
    return (
        '<aside class="content-cloud-resource">'
        f"<strong>{title}</strong>{mirror_html}"
        f'<a href="{detail_url}">查看资源说明</a></aside>'
    )


def _render_node(node: dict[str, Any], context: RenderContext) -> str:
    node_type = node["type"]
    attrs = node.get("attrs", {})
    children = _render_children(node, context)

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
    if node_type == "image":
        source = html.escape(attrs["src"], quote=True)
        alt = html.escape(attrs.get("alt", ""), quote=True)
        title = attrs.get("title", "")
        title_html = f' title="{html.escape(title, quote=True)}"' if title else ""
        size_html = "".join(
            f' {name}="{attrs[name]}"'
            for name in ("width", "height")
            if attrs.get(name) is not None
        )
        caption = f"<figcaption>{html.escape(title)}</figcaption>" if title else ""
        return (
            f'<figure><img src="{source}" alt="{alt}"{title_html}{size_html} '
            f'loading="lazy" decoding="async">{caption}</figure>'
        )
    if node_type == "callout":
        variant = attrs.get("variant", "info")
        title = html.escape(attrs.get("title", "提示"))
        return (
            f'<aside class="content-callout content-callout-{variant}">'
            f"<strong>{title}</strong>{children}</aside>"
        )
    if node_type == "equation":
        return _render_equation(attrs["latex"])
    if node_type == "standardReference":
        return _render_standard_reference(attrs["standardId"], context)
    if node_type == "parameterCard":
        name = html.escape(attrs["name"])
        value = html.escape(attrs["value"])
        unit = html.escape(attrs.get("unit", ""))
        note = html.escape(attrs.get("note", ""))
        unit_html = f'<span class="parameter-unit">{unit}</span>' if unit else ""
        note_html = f'<dd class="parameter-note">{note}</dd>' if note else ""
        return (
            '<dl class="content-parameter-card">'
            f"<dt>{name}</dt><dd><span>{value}</span>{unit_html}</dd>{note_html}</dl>"
        )
    if node_type == "cloudResource":
        return _render_cloud_resource(attrs["resourceId"], context)

    fallback_name = attrs.get("blockType", node_type) if node_type == "legacyBlock" else node_type
    node_name = html.escape(str(fallback_name), quote=True)
    return (
        f'<div class="content-unsupported-node" data-node-type="{node_name}">'
        f'<p>暂不支持的内容块：{html.escape(str(fallback_name))}</p>{children}</div>'
    )


def render_document(value: Any | ValidatedDocument, *, user=None) -> str:
    validated = value if isinstance(value, ValidatedDocument) else validate_document(value)
    rendered = _render_node(validated.doc, RenderContext(user=user))
    return nh3.clean(
        rendered,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_LINK_SCHEMES,
        link_rel="noopener noreferrer",
    )
