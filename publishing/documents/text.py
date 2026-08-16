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
}


def _walk(node: dict[str, Any], output: list[str]) -> None:
    node_type = node.get("type")
    if node_type == "text":
        output.append(node.get("text", ""))
        return
    if node_type == "hardBreak":
        output.append("\n")
        return
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
