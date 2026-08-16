import hashlib
import json
import mimetypes
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from django.db import IntegrityError
from django.utils import timezone
from markdown_it import MarkdownIt
from wagtail.images import get_image_model

from content.models import (
    AboutPage,
    ArticleIndexPage,
    ArticlePage,
    NoteIndexPage,
    NotePage,
    ProjectIndexPage,
    ProjectPage,
    ToolIndexPage,
    ToolPage,
)
from content.models import (
    Topic as LegacyTopic,
)
from core.models import HomePage
from notifications.models import Favorite, ItemSubscription
from publishing.documents import CURRENT_SCHEMA_VERSION, extract_text, validate_document
from publishing.models import (
    Article,
    Asset,
    ContentEntry,
    Note,
    Project,
    SiteProfile,
    Tool,
    Topic,
)
from publishing.services.revisions import snapshot_content

CONTENT_MODELS = {
    ContentEntry.Kind.PROJECT: (ProjectPage, Project),
    ContentEntry.Kind.ARTICLE: (ArticlePage, Article),
    ContentEntry.Kind.NOTE: (NotePage, Note),
    ContentEntry.Kind.TOOL: (ToolPage, Tool),
}
INDEX_MODELS = {
    "project_intro": ProjectIndexPage,
    "article_intro": ArticleIndexPage,
    "note_intro": NoteIndexPage,
    "tool_intro": ToolIndexPage,
}
KIND_URL_PREFIX = {
    ContentEntry.Kind.PROJECT: "projects",
    ContentEntry.Kind.ARTICLE: "articles",
    ContentEntry.Kind.NOTE: "notes",
    ContentEntry.Kind.TOOL: "tools",
}
SAFE_LINK_SCHEMES = {"http", "https", "mailto"}
WHITESPACE_RE = re.compile(r"\s+")


@dataclass
class ConversionIssue:
    severity: str
    code: str
    source_model: str
    source_id: int | None
    field: str
    message: str
    block_index: int | None = None
    block_type: str = ""
    raw: Any = None


@dataclass
class ConversionResult:
    document: dict[str, Any]
    issues: list[ConversionIssue] = field(default_factory=list)


@dataclass
class MigrationReport:
    mode: str = "import"
    created: dict[str, int] = field(default_factory=dict)
    updated: dict[str, int] = field(default_factory=dict)
    issues: list[ConversionIssue] = field(default_factory=list)
    differences: list[dict[str, Any]] = field(default_factory=list)

    @property
    def critical_count(self):
        return sum(issue.severity == "critical" for issue in self.issues) + len(self.differences)

    def count(self, bucket: str, name: str):
        values = getattr(self, bucket)
        values[name] = values.get(name, 0) + 1

    def as_dict(self):
        return {
            "schema_version": 1,
            "mode": self.mode,
            "created": self.created,
            "updated": self.updated,
            "issues": [asdict(issue) for issue in self.issues],
            "differences": self.differences,
            "critical_count": self.critical_count,
        }

    def write(self, path):
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.as_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


@dataclass
class _Element:
    tag: str
    attrs: dict[str, str]
    children: list[Any] = field(default_factory=list)


class _HTMLTreeParser(HTMLParser):
    VOID_TAGS = {"br", "hr", "img", "meta", "link", "input"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Element("root", {})
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _Element(tag.lower(), dict(attrs))
        self.stack[-1].children.append(node)
        if node.tag not in self.VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in self.VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        wanted = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == wanted:
                del self.stack[index:]
                return

    def handle_data(self, data):
        if data:
            self.stack[-1].children.append(data)


def _safe_href(value):
    value = str(value or "").strip()
    if value.startswith(("/", "#")) and not value.startswith("//"):
        return value
    try:
        return value if urlsplit(value).scheme.lower() in SAFE_LINK_SCHEMES else ""
    except ValueError:
        return ""


def _text_node(text, marks=None):
    if not text:
        return None
    node = {"type": "text", "text": text}
    if marks:
        node["marks"] = marks
    return node


def _inline_nodes(node, marks=None):
    marks = list(marks or [])
    if isinstance(node, str):
        text = _text_node(node, marks)
        return [text] if text else []
    if node.tag == "br":
        return [{"type": "hardBreak"}]

    mark = None
    if node.tag in {"strong", "b"}:
        mark = {"type": "bold"}
    elif node.tag in {"em", "i"}:
        mark = {"type": "italic"}
    elif node.tag in {"s", "strike", "del"}:
        mark = {"type": "strike"}
    elif node.tag == "u":
        mark = {"type": "underline"}
    elif node.tag == "code":
        mark = {"type": "code"}
    elif node.tag == "a":
        href = _safe_href(node.attrs.get("href"))
        if href:
            attrs = {"href": href}
            if node.attrs.get("title"):
                attrs["title"] = node.attrs["title"][:300]
            mark = {"type": "link", "attrs": attrs}
    if mark:
        marks.append(mark)

    result = []
    for child in node.children:
        result.extend(_inline_nodes(child, marks))
    return result


def _paragraph(children):
    content = []
    for child in children:
        content.extend(_inline_nodes(child))
    node = {"type": "paragraph"}
    if content:
        node["content"] = content
    return node


def _list_item(node):
    content = []
    inline = []
    for child in node.children:
        if isinstance(child, _Element) and child.tag in {
            "p",
            "ul",
            "ol",
            "blockquote",
            "pre",
        }:
            if inline:
                content.append(_paragraph(inline))
                inline = []
            content.extend(_block_nodes(child))
        else:
            inline.append(child)
    if inline or not content:
        content.insert(0, _paragraph(inline))
    return {"type": "listItem", "content": content}


def _block_nodes(node):
    if isinstance(node, str):
        return [_paragraph([node])] if node.strip() else []
    if node.tag in {"p", "div", "section", "article"}:
        contains_blocks = any(
            isinstance(child, _Element)
            and child.tag in {"p", "h1", "h2", "h3", "h4", "ul", "ol", "blockquote", "pre", "hr"}
            for child in node.children
        )
        if not contains_blocks:
            return [_paragraph(node.children)]
        result = []
        inline = []
        for child in node.children:
            if isinstance(child, _Element) and child.tag in {
                "p",
                "h1",
                "h2",
                "h3",
                "h4",
                "ul",
                "ol",
                "blockquote",
                "pre",
                "hr",
            }:
                if inline:
                    result.append(_paragraph(inline))
                    inline = []
                result.extend(_block_nodes(child))
            else:
                inline.append(child)
        if inline:
            result.append(_paragraph(inline))
        return result
    if node.tag in {"h1", "h2", "h3", "h4"}:
        level = 2 if node.tag in {"h1", "h2"} else 3
        result = {"type": "heading", "attrs": {"level": level}}
        content = []
        for child in node.children:
            content.extend(_inline_nodes(child))
        if content:
            result["content"] = content
        return [result]
    if node.tag in {"ul", "ol"}:
        attrs = {}
        if node.tag == "ol":
            try:
                start = int(node.attrs.get("start", "1"))
            except ValueError:
                start = 1
            if start != 1:
                attrs["start"] = max(1, min(start, 1_000_000))
        result = {"type": "bulletList" if node.tag == "ul" else "orderedList"}
        if attrs:
            result["attrs"] = attrs
        result["content"] = [
            _list_item(child)
            for child in node.children
            if isinstance(child, _Element) and child.tag == "li"
        ]
        return [result]
    if node.tag == "blockquote":
        children = []
        for child in node.children:
            children.extend(_block_nodes(child))
        return [{"type": "blockquote", "content": children or [_paragraph([])]}]
    if node.tag == "pre":
        text = "".join(_plain_text(child) for child in node.children)
        return [{"type": "codeBlock", "content": [{"type": "text", "text": text}]}]
    if node.tag == "hr":
        return [{"type": "horizontalRule"}]
    return [_paragraph([node])]


def _plain_text(node):
    if isinstance(node, str):
        return node
    return "".join(_plain_text(child) for child in node.children)


def html_to_nodes(source):
    parser = _HTMLTreeParser()
    parser.feed(str(source or ""))
    parser.close()
    result = []
    inline = []
    block_tags = {
        "p",
        "div",
        "section",
        "article",
        "h1",
        "h2",
        "h3",
        "h4",
        "ul",
        "ol",
        "blockquote",
        "pre",
        "hr",
    }
    for child in parser.root.children:
        if isinstance(child, _Element) and child.tag in block_tags:
            if inline:
                result.append(_paragraph(inline))
                inline = []
            result.extend(_block_nodes(child))
        else:
            inline.append(child)
    if inline:
        result.append(_paragraph(inline))
    return result


def _json_safe(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "source") and isinstance(value.source, str):
        return value.source
    if hasattr(value, "file") and hasattr(value, "pk"):
        return {
            "id": value.pk,
            "title": str(getattr(value, "title", value)),
            "file": str(getattr(value.file, "name", "")),
        }
    if hasattr(value, "items"):
        return {str(key): _json_safe(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)) or (
        hasattr(value, "__iter__") and not isinstance(value, (bytes, bytearray))
    ):
        try:
            return [_json_safe(child) for child in value]
        except TypeError:
            pass
    if hasattr(value, "pk"):
        return {"id": value.pk, "label": str(value)}
    return str(value)


def _value_dict(value):
    if isinstance(value, dict):
        return value
    if hasattr(value, "items"):
        return dict(value.items())
    return {}


def _text(value):
    if hasattr(value, "source"):
        return str(value.source)
    return str(value or "")


def _tiptap_text(value, *, marks=None):
    node = _text_node(str(value or ""), marks)
    return [node] if node else []


def _simple_paragraph(value, *, marks=None):
    content = _tiptap_text(value, marks=marks)
    node = {"type": "paragraph"}
    if content:
        node["content"] = content
    return node


def _table_nodes(value):
    raw = _value_dict(value)
    rows = raw.get("data", value if isinstance(value, list) else []) or []
    first_row_header = bool(raw.get("first_row_is_table_header"))
    first_col_header = bool(raw.get("first_col_is_header"))
    table_rows = []
    for row_index, row in enumerate(rows):
        cells = []
        for column_index, cell in enumerate(row or []):
            node_type = (
                "tableHeader"
                if (first_row_header and row_index == 0) or (first_col_header and column_index == 0)
                else "tableCell"
            )
            cells.append(
                {
                    "type": node_type,
                    "content": [_simple_paragraph("" if cell is None else cell)],
                }
            )
        table_rows.append({"type": "tableRow", "content": cells})
    return {"type": "table", "content": table_rows}


def _image_node(image, asset_map, *, alt="", title=""):
    if image is None or getattr(image, "pk", None) not in asset_map:
        return None
    asset = asset_map[image.pk]
    attrs = {
        "assetId": asset.pk,
        "src": asset.file.url,
        "alt": str(alt or getattr(image, "title", ""))[:300],
        "title": str(title or "")[:300],
    }
    for name in ("width", "height"):
        value = getattr(image, name, None)
        if isinstance(value, int) and 0 < value <= 12_000:
            attrs[name] = value
    return {"type": "image", "attrs": attrs}


def _legacy_block(block_type, value):
    raw_json = json.dumps(_json_safe(value), ensure_ascii=False, separators=(",", ":"))
    chunks = [raw_json[index : index + 19_000] for index in range(0, len(raw_json), 19_000)]
    return {
        "type": "legacyBlock",
        "attrs": {"blockType": block_type[:64], "rawChunks": chunks},
    }


def _iter_blocks(stream):
    for block in stream or []:
        if isinstance(block, dict):
            yield block.get("type") or block.get("block_type"), block.get("value")
        else:
            yield block.block_type, block.value


def streamfield_to_document(
    stream,
    *,
    asset_map=None,
    source_model="StreamField",
    source_id=None,
    field_name="body",
):
    asset_map = asset_map or {}
    nodes = []
    issues = []
    markdown = MarkdownIt("commonmark", {"html": False})
    for index, (block_type, value) in enumerate(_iter_blocks(stream)):
        raw = _value_dict(value)
        converted = []
        if block_type == "heading":
            converted = [
                {
                    "type": "heading",
                    "attrs": {"level": 2},
                    "content": _tiptap_text(value),
                }
            ]
        elif block_type == "section_heading":
            converted = [
                {
                    "type": "heading",
                    "attrs": {"level": 2 if raw.get("level") == "h2" else 3},
                    "content": _tiptap_text(raw.get("text")),
                }
            ]
        elif block_type == "paragraph":
            converted = html_to_nodes(_text(value))
        elif block_type == "markdown":
            converted = html_to_nodes(markdown.render(_text(value)))
        elif block_type == "divider":
            converted = [{"type": "horizontalRule"}]
        elif block_type == "callout":
            variant = raw.get("kind", "info")
            if variant in {"note", "experience"}:
                variant = "info"
            converted = [
                {
                    "type": "callout",
                    "attrs": {
                        "variant": variant if variant in {"info", "tip", "warning"} else "info",
                        "title": str(raw.get("title") or "提示")[:120],
                    },
                    "content": html_to_nodes(_text(raw.get("content"))) or [_simple_paragraph("")],
                }
            ]
        elif block_type == "equation":
            latex = str(raw.get("latex") or "").strip()
            if latex:
                converted.append({"type": "equation", "attrs": {"latex": latex[:4000]}})
                details = []
                if raw.get("number"):
                    details.append(f"公式编号：{raw['number']}")
                if raw.get("caption"):
                    details.append(str(raw["caption"]))
                if details:
                    converted.append(_simple_paragraph("；".join(details)))
                variables = raw.get("variables") or []
                if variables:
                    converted.append(
                        _table_nodes(
                            {
                                "data": [
                                    ["变量", "含义", "单位"],
                                    *[
                                        [item.get("symbol"), item.get("meaning"), item.get("unit")]
                                        for item in variables
                                    ],
                                ],
                                "first_row_is_table_header": True,
                            }
                        )
                    )
        elif block_type == "reference":
            title = (
                " ".join(
                    str(raw.get(name) or "").strip()
                    for name in ("identifier", "title_zh")
                    if raw.get(name)
                )
                or "资料引用"
            )
            lines = []
            for label, name in (
                ("英文名", "title_en"),
                ("版本", "edition"),
                ("条文", "clause"),
                ("页码", "pages"),
                ("摘要", "excerpt"),
                ("来源", "organization"),
                ("查阅日期", "accessed_on"),
            ):
                if raw.get(name):
                    lines.append(_simple_paragraph(f"{label}：{raw[name]}"))
            if raw.get("source_url"):
                href = _safe_href(raw["source_url"])
                if href:
                    lines.append(
                        _simple_paragraph(
                            "查看来源",
                            marks=[{"type": "link", "attrs": {"href": href}}],
                        )
                    )
            converted = [
                {
                    "type": "callout",
                    "attrs": {"variant": "info", "title": title[:120]},
                    "content": lines or [_simple_paragraph("")],
                }
            ]
            if raw.get("editor_note"):
                issues.append(
                    ConversionIssue(
                        "warning",
                        "private_editor_note",
                        source_model,
                        source_id,
                        field_name,
                        "引用块的旧编辑备注仅保存在迁移报告中，不进入公开正文。",
                        index,
                        block_type,
                        _json_safe(value),
                    )
                )
        elif block_type == "captioned_image":
            image = _image_node(
                raw.get("image"),
                asset_map,
                alt=raw.get("alt_text"),
                title=raw.get("caption"),
            )
            if image:
                converted.append(image)
                if raw.get("source"):
                    converted.append(_simple_paragraph(f"图片来源：{raw['source']}"))
        elif block_type == "image":
            image = _image_node(value, asset_map)
            if image:
                converted = [image]
        elif block_type == "data_table":
            if raw.get("title"):
                converted.append(
                    {
                        "type": "heading",
                        "attrs": {"level": 3},
                        "content": _tiptap_text(raw["title"]),
                    }
                )
            converted.append(_table_nodes(raw.get("table") or {}))
            notes = [
                f"{label}：{raw[name]}"
                for label, name in (("单位", "units"), ("来源", "source"), ("注", "notes"))
                if raw.get(name)
            ]
            if notes:
                converted.append(_simple_paragraph("；".join(notes)))
        elif block_type == "table":
            converted = [_table_nodes(value)]
        elif block_type == "parameter_card":
            if raw.get("title"):
                converted.append(
                    {
                        "type": "heading",
                        "attrs": {"level": 3},
                        "content": _tiptap_text(raw["title"]),
                    }
                )
            converted.extend(
                {
                    "type": "parameterCard",
                    "attrs": {
                        "name": str(item.get("name") or "")[:120],
                        "value": str(item.get("value") or "")[:120],
                        "unit": str(item.get("unit") or "")[:40],
                        "note": str(item.get("note") or "")[:500],
                    },
                }
                for item in (raw.get("items") or [])
                if item.get("name") and item.get("value")
            )
        elif block_type == "attachment":
            document = raw.get("document")
            href = _safe_href(getattr(getattr(document, "file", None), "url", ""))
            label = raw.get("display_name") or getattr(document, "title", "附件")
            if href:
                converted.append(
                    _simple_paragraph(
                        label,
                        marks=[{"type": "link", "attrs": {"href": href}}],
                    )
                )
                details = "；".join(
                    str(raw[name]) for name in ("version", "description") if raw.get(name)
                )
                if details:
                    converted.append(_simple_paragraph(details))
        elif block_type == "external_resource":
            href = _safe_href(raw.get("url"))
            label = str(raw.get("title") or href or "外部资料")
            converted.append(
                _simple_paragraph(
                    label,
                    marks=[{"type": "link", "attrs": {"href": href}}] if href else None,
                )
            )
            details = "；".join(
                str(raw[name]) for name in ("provider", "version", "description") if raw.get(name)
            )
            if details:
                converted.append(_simple_paragraph(details))
        elif block_type == "code":
            language = re.sub(r"[^A-Za-z0-9_+.#-]", "", str(raw.get("language") or "text"))[:40]
            converted = [
                {
                    "type": "codeBlock",
                    "attrs": {"language": language},
                    "content": _tiptap_text(raw.get("code")),
                }
            ]
            if raw.get("caption"):
                converted.append(_simple_paragraph(raw["caption"]))

        if not converted:
            converted = [_legacy_block(str(block_type or "unknown"), value)]
            issues.append(
                ConversionIssue(
                    "critical",
                    "unmapped_block",
                    source_model,
                    source_id,
                    field_name,
                    "旧内容块无法可靠转换，原始数据已保留。",
                    index,
                    str(block_type or "unknown"),
                    _json_safe(value),
                )
            )
        nodes.extend(converted)

    document = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "doc": {"type": "doc", "content": nodes or [{"type": "paragraph"}]},
    }
    validate_document(document)
    return ConversionResult(document, issues)


def _normalized_hash(document):
    text = WHITESPACE_RE.sub(" ", extract_text(document)).strip()
    return hashlib.sha256(text.encode("utf-8"), usedforsecurity=False).hexdigest()


def _media_references(document):
    references = []

    def walk(node):
        if node.get("type") == "image":
            attrs = node.get("attrs", {})
            references.append((attrs.get("assetId"), attrs.get("src")))
        for child in node.get("content", []):
            walk(child)

    walk(document["doc"])
    return sorted(references)


def _latest_object(page):
    revision = page.get_latest_revision()
    return revision.as_object() if revision else page.specific


def _live_object(page):
    revision = page.live_revision
    return revision.as_object() if revision else (page.specific if page.live else None)


class LegacyConverter:
    def __init__(self, *, actor):
        self.actor = actor
        self.report = MigrationReport(mode="import")
        self.asset_map = {}
        self.project_map = {}
        self.article_map = {}

    def _author(self, value):
        return getattr(value, "owner", None) or self.actor

    def _upsert_topic(self, source):
        target = Topic.objects.filter(legacy_source_id=source.pk).first()
        created = target is None
        if target is None:
            target = Topic.objects.filter(slug=source.slug).first()
            if target and target.legacy_source_id not in (None, source.pk):
                raise IntegrityError(f"主题别名 {source.slug} 已绑定其他旧记录")
        if target is None:
            target = Topic(legacy_source_id=source.pk)
        target.legacy_source_id = source.pk
        target.name = source.name
        target.slug = source.slug
        target.description = source.description
        target.accent = source.accent
        target.save()
        self.report.count("created" if created else "updated", "topics")
        return target

    def import_topics(self):
        return {source.pk: self._upsert_topic(source) for source in LegacyTopic.objects.all()}

    def import_images(self):
        image_model = get_image_model()
        for image in image_model.objects.all().order_by("pk"):
            target = Asset.objects.filter(legacy_source_id=image.pk).first()
            created = target is None
            if target is None:
                target = Asset(legacy_source_id=image.pk)
            uploader = getattr(image, "uploaded_by_user", None) or self.actor
            if uploader is None:
                raise ValueError(f"图片 #{image.pk} 缺少上传人，请指定迁移操作者")
            file_name = str(image.file.name)
            mime_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
            try:
                byte_size = image.file_size or image.file.size
            except (OSError, ValueError):
                byte_size = image.file_size or 0
            target.kind = Asset.Kind.IMAGE
            target.file.name = file_name
            target.original_name = Path(file_name).name
            target.title = image.title
            target.alt_text = image.title
            target.mime_type = mime_type
            target.byte_size = byte_size
            target.width = image.width
            target.height = image.height
            target.uploaded_by = uploader
            target.save()
            self.asset_map[image.pk] = target
            self.report.count("created" if created else "updated", "images")

    def _document(self, page, field_name="body"):
        result = streamfield_to_document(
            getattr(page, field_name),
            asset_map=self.asset_map,
            source_model=page.__class__.__name__,
            source_id=page.pk,
            field_name=field_name,
        )
        self.report.issues.extend(result.issues)
        return result.document

    def _resolve_target(self, model, source_id, slug, kind):
        target = model.objects.filter(legacy_source_id=source_id).first()
        created = target is None
        if target is None:
            target = model.objects.filter(kind=kind, slug=slug).first()
            if target and target.legacy_source_id not in (None, source_id):
                raise IntegrityError(f"{kind} 别名 {slug} 已绑定其他旧记录")
        return target or model(legacy_source_id=source_id), created

    def _extra_fields(self, page, kind):
        if kind == ContentEntry.Kind.PROJECT:
            return {
                "project_status": page.status,
                "started_on": page.started_on,
                "completed_on": page.completed_on,
            }
        parent = self.project_map.get(getattr(page, "project_id", None))
        if kind == ContentEntry.Kind.ARTICLE:
            return {
                "published_on": page.published_on,
                "reading_minutes": page.reading_minutes,
                "parent_project": parent,
            }
        if kind == ContentEntry.Kind.NOTE:
            return {
                "noted_on": page.noted_on,
                "parent_project": parent,
                "promoted_article": self.article_map.get(page.promoted_article_id),
            }
        return {
            "launched_on": page.launched_on,
            "tool_status": page.status,
            "service_url": page.service_url,
            "source_url": page.source_url,
            "parent_project": parent,
        }

    def _apply_page(self, source, model, kind, topic_map):
        draft = _latest_object(source)
        live = _live_object(source)
        target, created = self._resolve_target(model, source.pk, draft.slug, kind)
        author = self._author(draft)
        if author is None:
            raise ValueError(f"{draft.__class__.__name__} #{draft.pk} 缺少作者，请指定迁移操作者")
        target.legacy_source_id = source.pk
        target.author = author
        target.title = draft.title
        target.slug = draft.slug
        target.summary = draft.summary
        target.featured = getattr(draft, "featured", False)
        target.body_json = self._document(draft)
        target.cover_asset = self.asset_map.get(getattr(draft, "cover_image_id", None))
        for name, value in self._extra_fields(draft, kind).items():
            setattr(target, name, value)
        target.status = ContentEntry.Status.DRAFT
        target.published_at = None
        target.published_body_json = None
        target.published_title = ""
        target.published_slug = ""
        target.published_summary = ""
        target.published_featured = False
        target.published_cover_asset = None
        target.published_metadata = {}
        target.save()
        target.topics.set(topic_map[item.pk] for item in draft.topics.all())

        if live is not None:
            live_document = self._document(live)
            target.published_body_json = live_document
            target.published_title = live.title
            target.published_slug = live.slug
            target.published_summary = live.summary
            target.published_featured = getattr(live, "featured", False)
            target.published_cover_asset = self.asset_map.get(getattr(live, "cover_image_id", None))
            live_extra = self._extra_fields(live, kind)
            current_extra = {name: getattr(target, name) for name in live_extra}
            for name, value in live_extra.items():
                setattr(target, name, value)
            target.published_metadata = {
                "schema_version": 1,
                "kind": kind,
                "type": snapshot_content(target)["type"],
            }
            for name, value in current_extra.items():
                setattr(target, name, value)
            target.status = ContentEntry.Status.PUBLISHED
            target.published_at = (
                source.first_published_at or source.last_published_at or timezone.now()
            )
            target.save()
            target.published_topics.set(topic_map[item.pk] for item in live.topics.all())
        else:
            target.published_topics.clear()
        self.report.count("created" if created else "updated", f"{kind}s")
        return target

    def import_content(self, topic_map):
        for kind in (
            ContentEntry.Kind.PROJECT,
            ContentEntry.Kind.ARTICLE,
            ContentEntry.Kind.NOTE,
            ContentEntry.Kind.TOOL,
        ):
            legacy_model, target_model = CONTENT_MODELS[kind]
            for source in legacy_model.objects.all().order_by("pk"):
                target = self._apply_page(source, target_model, kind, topic_map)
                if kind == ContentEntry.Kind.PROJECT:
                    self.project_map[source.pk] = target
                elif kind == ContentEntry.Kind.ARTICLE:
                    self.article_map[source.pk] = target

    def import_profile(self):
        profile = SiteProfile.objects.first() or SiteProfile()
        home = HomePage.objects.order_by("pk").first()
        if home:
            home = _live_object(home) or _latest_object(home)
            profile.site_name = (home.seo_title or home.title or profile.site_name)[:120]
            profile.tagline = (home.search_description or "")[:240]
        for field_name, model in INDEX_MODELS.items():
            page = model.objects.order_by("pk").first()
            if page:
                page = _live_object(page) or _latest_object(page)
                setattr(profile, field_name, page.intro)
        about = AboutPage.objects.order_by("pk").first()
        if about:
            about = _live_object(about) or _latest_object(about)
            profile.about_intro = about.intro
            profile.about_body_json = self._document(about)
        profile.save()
        self.report.count("updated", "site_profile")

    def migrate_saved_references(self):
        mapping = {
            str(entry.legacy_source_id): str(entry.pk)
            for entry in ContentEntry.objects.exclude(legacy_source_id=None)
        }
        for model in (Favorite, ItemSubscription):
            for saved in model.objects.filter(item_type__in=CONTENT_MODELS):
                new_id = mapping.get(saved.object_id)
                if not new_id or new_id == saved.object_id:
                    continue
                duplicate = model.objects.filter(
                    user=saved.user,
                    item_type=saved.item_type,
                    object_id=new_id,
                ).exclude(pk=saved.pk)
                if duplicate.exists():
                    saved.delete()
                else:
                    saved.object_id = new_id
                    saved.save(update_fields={"object_id"})
                self.report.count("updated", model._meta.model_name)

    def run(self):
        topic_map = self.import_topics()
        self.import_images()
        self.import_content(topic_map)
        self.import_profile()
        self.migrate_saved_references()
        return self.report


class LegacyVerifier:
    def __init__(self):
        self.report = MigrationReport(mode="verify")
        self.asset_map = {
            asset.legacy_source_id: asset for asset in Asset.objects.exclude(legacy_source_id=None)
        }

    def _difference(self, *, model, source_id, field, expected, actual):
        self.report.differences.append(
            {
                "model": model,
                "source_id": source_id,
                "field": field,
                "expected": _json_safe(expected),
                "actual": _json_safe(actual),
            }
        )

    def _compare(self, source, target, field, expected, actual):
        if expected != actual:
            self._difference(
                model=source.__class__.__name__,
                source_id=source.pk,
                field=field,
                expected=expected,
                actual=actual,
            )

    def _expected_type_metadata(self, page, kind):
        if kind == ContentEntry.Kind.PROJECT:
            return {
                "project_status": page.status,
                "started_on": page.started_on.isoformat(),
                "completed_on": page.completed_on.isoformat() if page.completed_on else None,
            }
        parent = Project.objects.filter(legacy_source_id=page.project_id).first()
        if kind == ContentEntry.Kind.ARTICLE:
            return {
                "published_on": page.published_on.isoformat(),
                "reading_minutes": page.reading_minutes,
                "parent_project_id": parent.pk if parent else None,
            }
        if kind == ContentEntry.Kind.NOTE:
            promoted = Article.objects.filter(legacy_source_id=page.promoted_article_id).first()
            return {
                "noted_on": page.noted_on.isoformat(),
                "parent_project_id": parent.pk if parent else None,
                "promoted_article_id": promoted.pk if promoted else None,
            }
        return {
            "launched_on": page.launched_on.isoformat(),
            "tool_status": page.status,
            "service_url": page.service_url,
            "source_url": page.source_url,
            "parent_project_id": parent.pk if parent else None,
        }

    def verify_counts(self):
        for kind, (legacy_model, _) in CONTENT_MODELS.items():
            self._compare(
                legacy_model(),
                None,
                f"count.{kind}",
                legacy_model.objects.count(),
                ContentEntry.objects.filter(kind=kind, legacy_source_id__isnull=False).count(),
            )
        self._compare(
            LegacyTopic(),
            None,
            "count.topics",
            LegacyTopic.objects.count(),
            Topic.objects.filter(legacy_source_id__isnull=False).count(),
        )
        image_model = get_image_model()
        self._compare(
            image_model(),
            None,
            "count.images",
            image_model.objects.count(),
            Asset.objects.filter(kind=Asset.Kind.IMAGE, legacy_source_id__isnull=False).count(),
        )

    def verify_topics(self):
        for source in LegacyTopic.objects.all():
            target = Topic.objects.filter(legacy_source_id=source.pk).first()
            if target is None:
                self._difference(
                    model="Topic",
                    source_id=source.pk,
                    field="record",
                    expected="present",
                    actual="missing",
                )
                continue
            for name in ("name", "slug", "description", "accent"):
                self._compare(source, target, name, getattr(source, name), getattr(target, name))

    def verify_images(self):
        for source in get_image_model().objects.all():
            target = self.asset_map.get(source.pk)
            if target is None:
                self._difference(
                    model="Image",
                    source_id=source.pk,
                    field="record",
                    expected="present",
                    actual="missing",
                )
                continue
            self._compare(source, target, "file", source.file.name, target.file.name)
            self._compare(source, target, "title", source.title, target.title)
            self._compare(source, target, "width", source.width, target.width)
            self._compare(source, target, "height", source.height, target.height)

    def verify_content(self):
        for kind, (legacy_model, target_model) in CONTENT_MODELS.items():
            for source in legacy_model.objects.all().order_by("pk"):
                draft = _latest_object(source)
                live = _live_object(source)
                target = target_model.objects.filter(legacy_source_id=source.pk).first()
                if target is None:
                    self._difference(
                        model=legacy_model.__name__,
                        source_id=source.pk,
                        field="record",
                        expected="present",
                        actual="missing",
                    )
                    continue
                expected_draft = streamfield_to_document(
                    draft.body,
                    asset_map=self.asset_map,
                    source_model=legacy_model.__name__,
                    source_id=source.pk,
                )
                self.report.issues.extend(expected_draft.issues)
                for name in ("title", "slug", "summary"):
                    self._compare(source, target, name, getattr(draft, name), getattr(target, name))
                self._compare(
                    source,
                    target,
                    "featured",
                    getattr(draft, "featured", False),
                    target.featured,
                )
                self._compare(
                    source,
                    target,
                    "cover_image",
                    getattr(draft, "cover_image_id", None),
                    getattr(target.cover_asset, "legacy_source_id", None),
                )
                self._compare(
                    source,
                    target,
                    "topics",
                    sorted(item.pk for item in draft.topics.all()),
                    sorted(target.topics.values_list("legacy_source_id", flat=True)),
                )
                expected_draft_type = self._expected_type_metadata(draft, kind)
                actual_draft_type = snapshot_content(target)["type"]
                self._compare(
                    source,
                    target,
                    "draft_type_metadata",
                    expected_draft_type,
                    actual_draft_type,
                )
                self._compare(
                    source,
                    target,
                    "draft_body_hash",
                    _normalized_hash(expected_draft.document),
                    _normalized_hash(target.body_json),
                )
                self._compare(
                    source,
                    target,
                    "draft_media",
                    _media_references(expected_draft.document),
                    _media_references(target.body_json),
                )
                expected_status = (
                    ContentEntry.Status.PUBLISHED if live else ContentEntry.Status.DRAFT
                )
                self._compare(source, target, "status", expected_status, target.status)
                if live:
                    expected_live = streamfield_to_document(
                        live.body,
                        asset_map=self.asset_map,
                        source_model=legacy_model.__name__,
                        source_id=source.pk,
                    )
                    self.report.issues.extend(expected_live.issues)
                    self._compare(
                        source, target, "published_title", live.title, target.published_title
                    )
                    self._compare(
                        source, target, "published_slug", live.slug, target.published_slug
                    )
                    self._compare(
                        source,
                        target,
                        "published_summary",
                        live.summary,
                        target.published_summary,
                    )
                    self._compare(
                        source,
                        target,
                        "published_featured",
                        getattr(live, "featured", False),
                        target.published_featured,
                    )
                    self._compare(
                        source,
                        target,
                        "published_cover_image",
                        getattr(live, "cover_image_id", None),
                        getattr(target.published_cover_asset, "legacy_source_id", None),
                    )
                    self._compare(
                        source,
                        target,
                        "published_topics",
                        sorted(item.pk for item in live.topics.all()),
                        sorted(target.published_topics.values_list("legacy_source_id", flat=True)),
                    )
                    self._compare(
                        source,
                        target,
                        "published_type_metadata",
                        self._expected_type_metadata(live, kind),
                        target.published_metadata.get("type", {}),
                    )
                    self._compare(
                        source,
                        target,
                        "public_url",
                        f"/{KIND_URL_PREFIX[kind]}/{live.slug}/",
                        target.get_absolute_url(),
                    )
                    self._compare(
                        source,
                        target,
                        "published_body_hash",
                        _normalized_hash(expected_live.document),
                        _normalized_hash(target.published_body_json),
                    )
                    self._compare(
                        source,
                        target,
                        "published_media",
                        _media_references(expected_live.document),
                        _media_references(target.published_body_json),
                    )

    def verify_profile(self):
        profile = SiteProfile.objects.first()
        if profile is None:
            self._difference(
                model="SiteProfile",
                source_id=None,
                field="record",
                expected="present",
                actual="missing",
            )
            return
        home = HomePage.objects.order_by("pk").first()
        if home:
            home = _live_object(home) or _latest_object(home)
            self._compare(
                home,
                profile,
                "site_name",
                (home.seo_title or home.title or profile.site_name)[:120],
                profile.site_name,
            )
            self._compare(
                home,
                profile,
                "tagline",
                (home.search_description or "")[:240],
                profile.tagline,
            )
        for field_name, model in INDEX_MODELS.items():
            source = model.objects.order_by("pk").first()
            if source:
                public_source = _live_object(source) or _latest_object(source)
                self._compare(
                    source,
                    profile,
                    field_name,
                    public_source.intro,
                    getattr(profile, field_name),
                )
        about = AboutPage.objects.order_by("pk").first()
        if about:
            about = _live_object(about) or _latest_object(about)
            expected = streamfield_to_document(
                about.body,
                asset_map=self.asset_map,
                source_model="AboutPage",
                source_id=about.pk,
            )
            self.report.issues.extend(expected.issues)
            self._compare(about, profile, "about_intro", about.intro, profile.about_intro)
            self._compare(
                about,
                profile,
                "about_body_hash",
                _normalized_hash(expected.document),
                _normalized_hash(profile.about_body_json),
            )

    def run(self):
        self.verify_counts()
        self.verify_topics()
        self.verify_images()
        self.verify_content()
        self.verify_profile()
        return self.report
