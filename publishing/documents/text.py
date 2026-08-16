import re
from typing import Any

from .schema import ValidatedDocument, validate_document

BLOCK_NODES = {
    "paragraph",
    "heading",
    "listItem",
    "blockquote",
    "codeBlock",
    "tableRow",
    "horizontalRule",
    "callout",
}


def _walk(node: dict[str, Any], output: list[str]) -> None:
    node_type = node.get("type")
    if node_type == "text":
        output.append(node.get("text", ""))
        return
    if node_type == "hardBreak":
        output.append("\n")
        return
    if node_type == "image":
        output.append(node.get("attrs", {}).get("alt", ""))
        output.append("\n")
        return
    if node_type == "equation":
        output.extend((node.get("attrs", {}).get("latex", ""), "\n"))
        return
    if node_type == "standardReference":
        output.extend((f"规范 #{node.get('attrs', {}).get('standardId', '')}", "\n"))
        return
    if node_type == "parameterCard":
        attrs = node.get("attrs", {})
        output.extend(
            (
                " ".join(
                    str(attrs.get(name, ""))
                    for name in ("name", "value", "unit", "note")
                    if attrs.get(name)
                ),
                "\n",
            )
        )
        return
    if node_type == "cloudResource":
        output.extend((f"资源 #{node.get('attrs', {}).get('resourceId', '')}", "\n"))
        return
    if node_type == "callout":
        title = node.get("attrs", {}).get("title", "")
        if title:
            output.extend((title, "\n"))
    for child in node.get("content", []):
        _walk(child, output)
    if node_type in BLOCK_NODES:
        output.append("\n")


def extract_text(value: Any | ValidatedDocument) -> str:
    validated = value if isinstance(value, ValidatedDocument) else validate_document(value)
    parts: list[str] = []
    _walk(validated.doc, parts)
    lines = [re.sub(r"[\t\f\v ]+", " ", line).strip() for line in "".join(parts).splitlines()]
    return "\n".join(line for line in lines if line)
