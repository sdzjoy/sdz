import copy
import json
import math
import re
from dataclasses import dataclass
from typing import Any

CURRENT_SCHEMA_VERSION = 1
MAX_DOCUMENT_BYTES = 1_000_000
MAX_DOCUMENT_DEPTH = 30
MAX_DOCUMENT_NODES = 10_000
MAX_TEXT_NODE_LENGTH = 100_000
MAX_TOTAL_TEXT_LENGTH = 500_000
MAX_ATTRIBUTE_DEPTH = 6
MAX_ATTRIBUTE_STRING_LENGTH = 20_000

TYPE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
LANGUAGE_PATTERN = re.compile(r"^[A-Za-z0-9_+.#-]{0,40}$")

KNOWN_NODES = {
    "doc",
    "paragraph",
    "text",
    "heading",
    "hardBreak",
    "horizontalRule",
    "bulletList",
    "orderedList",
    "listItem",
    "blockquote",
    "codeBlock",
    "table",
    "tableRow",
    "tableHeader",
    "tableCell",
}
KNOWN_MARKS = {"bold", "italic", "strike", "underline", "code", "link"}

NODE_ATTRIBUTES = {
    "orderedList": {"start"},
    "heading": {"level"},
    "codeBlock": {"language"},
    "tableCell": {"colspan", "rowspan", "colwidth"},
    "tableHeader": {"colspan", "rowspan", "colwidth"},
}
MARK_ATTRIBUTES = {
    "link": {"href", "title", "target", "rel", "class"},
}


class DocumentValidationError(ValueError):
    def __init__(self, code: str, message: str, path: str = "$"):
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = path

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


@dataclass(frozen=True)
class DocumentWarning:
    code: str
    message: str
    path: str


@dataclass(frozen=True)
class ValidatedDocument:
    schema_version: int
    doc: dict[str, Any]
    warnings: tuple[DocumentWarning, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "doc": copy.deepcopy(self.doc)}


def empty_document() -> dict[str, Any]:
    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "doc": {"type": "doc", "content": [{"type": "paragraph"}]},
    }


def _fail(code: str, message: str, path: str) -> None:
    raise DocumentValidationError(code, message, path)


def _validate_json_value(value: Any, path: str, depth: int = 0) -> None:
    if depth > MAX_ATTRIBUTE_DEPTH:
        _fail("attribute_depth", "属性嵌套过深", path)
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail("attribute_number", "属性数字必须是有限值", path)
        return
    if isinstance(value, str):
        if len(value) > MAX_ATTRIBUTE_STRING_LENGTH:
            _fail("attribute_length", "属性文本过长", path)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{path}[{index}]", depth + 1)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                _fail("attribute_key", "属性键必须是文本", path)
            _validate_json_value(item, f"{path}.{key}", depth + 1)
        return
    _fail("attribute_type", "属性包含不支持的数据类型", path)


def _validate_known_attributes(node_type: str, attrs: dict[str, Any], path: str) -> None:
    allowed = NODE_ATTRIBUTES.get(node_type, set())
    unexpected = set(attrs) - allowed
    if unexpected:
        _fail("node_attributes", f"{node_type} 包含不允许的属性", path)

    if node_type == "heading" and attrs.get("level") not in {2, 3}:
        _fail("heading_level", "标题级别只能是 2 或 3", f"{path}.level")
    if node_type == "orderedList":
        start = attrs.get("start", 1)
        if not isinstance(start, int) or isinstance(start, bool) or not 1 <= start <= 1_000_000:
            _fail("list_start", "有序列表起始值无效", f"{path}.start")
    if node_type == "codeBlock":
        language = attrs.get("language")
        if language is not None and (
            not isinstance(language, str) or not LANGUAGE_PATTERN.fullmatch(language)
        ):
            _fail("code_language", "代码语言标识无效", f"{path}.language")
    if node_type in {"tableCell", "tableHeader"}:
        for name in ("colspan", "rowspan"):
            value = attrs.get(name, 1)
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 20:
                _fail("table_span", "表格跨行或跨列值无效", f"{path}.{name}")
        colwidth = attrs.get("colwidth")
        if colwidth is not None and (
            not isinstance(colwidth, list)
            or len(colwidth) > 20
            or any(
                not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 10_000
                for value in colwidth
            )
        ):
            _fail("table_width", "表格列宽数据无效", f"{path}.colwidth")


def _validate_mark(mark: Any, path: str, warnings: list[DocumentWarning]) -> None:
    if not isinstance(mark, dict):
        _fail("mark_type", "文字标记必须是对象", path)
    mark_type = mark.get("type")
    if not isinstance(mark_type, str) or not TYPE_PATTERN.fullmatch(mark_type):
        _fail("mark_name", "文字标记名称无效", f"{path}.type")
    unexpected_keys = set(mark) - {"type", "attrs"}
    if unexpected_keys:
        _fail("mark_keys", "文字标记包含不允许的字段", path)
    attrs = mark.get("attrs", {})
    if not isinstance(attrs, dict):
        _fail("mark_attributes", "文字标记属性必须是对象", f"{path}.attrs")
    _validate_json_value(attrs, f"{path}.attrs")

    if mark_type not in KNOWN_MARKS:
        warnings.append(DocumentWarning("unknown_mark", "未知文字标记已保留但不会渲染", path))
        return
    allowed = MARK_ATTRIBUTES.get(mark_type, set())
    if set(attrs) - allowed:
        _fail("mark_attributes", f"{mark_type} 包含不允许的属性", f"{path}.attrs")
    if mark_type == "link":
        href = attrs.get("href")
        if not isinstance(href, str) or not href or len(href) > 2_000:
            _fail("link_href", "链接地址无效", f"{path}.attrs.href")
        for name in ("title", "target", "rel", "class"):
            value = attrs.get(name)
            if value is not None and not isinstance(value, str):
                _fail("link_attribute", "链接属性必须是文本或空值", f"{path}.attrs.{name}")


def _validate_node(
    node: Any,
    path: str,
    depth: int,
    state: dict[str, int],
    warnings: list[DocumentWarning],
) -> None:
    if depth > MAX_DOCUMENT_DEPTH:
        _fail("document_depth", "正文结构嵌套过深", path)
    if not isinstance(node, dict):
        _fail("node_type", "正文节点必须是对象", path)

    state["nodes"] += 1
    if state["nodes"] > MAX_DOCUMENT_NODES:
        _fail("node_count", "正文节点数量过多", path)

    node_type = node.get("type")
    if not isinstance(node_type, str) or not TYPE_PATTERN.fullmatch(node_type):
        _fail("node_name", "正文节点名称无效", f"{path}.type")

    allowed_keys = {"type", "attrs", "content", "marks", "text"}
    if set(node) - allowed_keys:
        _fail("node_keys", "正文节点包含不允许的字段", path)

    attrs = node.get("attrs", {})
    if not isinstance(attrs, dict):
        _fail("node_attributes", "正文节点属性必须是对象", f"{path}.attrs")
    _validate_json_value(attrs, f"{path}.attrs")

    if node_type in KNOWN_NODES:
        _validate_known_attributes(node_type, attrs, f"{path}.attrs")
    else:
        warnings.append(DocumentWarning("unknown_node", "未知节点已保留并将安全降级", path))

    text = node.get("text")
    if node_type == "text":
        if not isinstance(text, str):
            _fail("text_type", "文本节点缺少文本内容", f"{path}.text")
        if len(text) > MAX_TEXT_NODE_LENGTH:
            _fail("text_length", "单个文本节点过长", f"{path}.text")
        state["text"] += len(text)
        if state["text"] > MAX_TOTAL_TEXT_LENGTH:
            _fail("total_text_length", "正文文本总长度过长", f"{path}.text")
        if "content" in node:
            _fail("text_content", "文本节点不能包含子节点", f"{path}.content")
    elif "text" in node:
        _fail("node_text", "非文本节点不能直接包含文本", f"{path}.text")

    marks = node.get("marks", [])
    if not isinstance(marks, list):
        _fail("marks_type", "文字标记必须是数组", f"{path}.marks")
    for index, mark in enumerate(marks):
        _validate_mark(mark, f"{path}.marks[{index}]", warnings)

    content = node.get("content", [])
    if not isinstance(content, list):
        _fail("content_type", "子节点必须是数组", f"{path}.content")
    for index, child in enumerate(content):
        _validate_node(child, f"{path}.content[{index}]", depth + 1, state, warnings)


def validate_document(value: Any) -> ValidatedDocument:
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, UnicodeEncodeError, ValueError) as error:
        raise DocumentValidationError("json_type", "正文必须是可序列化的 JSON") from error
    if len(encoded) > MAX_DOCUMENT_BYTES:
        raise DocumentValidationError("document_size", "正文数据过大")
    if not isinstance(value, dict):
        raise DocumentValidationError("document_type", "正文必须是对象")
    if set(value) - {"schema_version", "doc"}:
        raise DocumentValidationError("document_keys", "正文包含不允许的顶层字段")
    if value.get("schema_version") != CURRENT_SCHEMA_VERSION:
        raise DocumentValidationError(
            "schema_version",
            f"暂不支持正文版本 {value.get('schema_version')!r}",
            "$.schema_version",
        )
    doc = value.get("doc")
    if not isinstance(doc, dict) or doc.get("type") != "doc":
        raise DocumentValidationError("document_root", "正文根节点必须是 doc", "$.doc")

    warnings: list[DocumentWarning] = []
    state = {"nodes": 0, "text": 0}
    _validate_node(doc, "$.doc", 0, state, warnings)
    return ValidatedDocument(CURRENT_SCHEMA_VERSION, copy.deepcopy(doc), tuple(warnings))
