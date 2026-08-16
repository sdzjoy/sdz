import pytest

from publishing.documents import (
    DocumentValidationError,
    empty_document,
    extract_text,
    render_document,
    validate_document,
)
from publishing.documents.schema import MAX_DOCUMENT_DEPTH


def document(*content):
    return {"schema_version": 1, "doc": {"type": "doc", "content": list(content)}}


def text(value, *marks):
    node = {"type": "text", "text": value}
    if marks:
        node["marks"] = list(marks)
    return node


def paragraph(*content):
    return {"type": "paragraph", "content": list(content)}


def test_empty_document_is_valid_and_safe_to_render():
    validated = validate_document(empty_document())

    assert validated.schema_version == 1
    assert render_document(validated) == "<p></p>"
    assert extract_text(validated) == ""


def test_render_document_escapes_text_and_keeps_supported_marks():
    value = document(
        {
            "type": "heading",
            "attrs": {"level": 2},
            "content": [text("冷源 & 负荷")],
        },
        paragraph(
            text("详见 "),
            text(
                "GB 50736",
                {"type": "bold"},
                {"type": "link", "attrs": {"href": "https://example.com/a?b=1&c=2"}},
            ),
            text(" <script>alert(1)</script>"),
        ),
    )

    rendered = render_document(value)

    assert "<h2>冷源 &amp; 负荷</h2>" in rendered
    assert '<a href="https://example.com/a?b=1&amp;c=2" rel="noopener noreferrer">' in rendered
    assert "<strong>GB 50736</strong>" in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    assert "<script>" not in rendered


def test_render_document_rejects_dangerous_link_without_losing_text():
    value = document(
        paragraph(
            text(
                "不要执行",
                {"type": "link", "attrs": {"href": "javascript:alert(1)", "target": "_blank"}},
            )
        )
    )

    rendered = render_document(value)

    assert rendered == "<p>不要执行</p>"
    assert "javascript:" not in rendered


def test_nested_lists_tables_and_text_extraction():
    value = document(
        {
            "type": "orderedList",
            "attrs": {"start": 3},
            "content": [
                {"type": "listItem", "content": [paragraph(text("一次侧"))]},
                {"type": "listItem", "content": [paragraph(text("二次侧"))]},
            ],
        },
        {
            "type": "table",
            "content": [
                {
                    "type": "tableRow",
                    "content": [
                        {
                            "type": "tableHeader",
                            "attrs": {"colspan": 2, "rowspan": 1, "colwidth": None},
                            "content": [paragraph(text("参数"))],
                        }
                    ],
                },
                {
                    "type": "tableRow",
                    "content": [
                        {
                            "type": "tableCell",
                            "attrs": {"colspan": 1, "rowspan": 1, "colwidth": None},
                            "content": [paragraph(text("温度"))],
                        }
                    ],
                },
            ],
        },
    )

    rendered = render_document(value)

    assert '<ol start="3">' in rendered
    assert '<th colspan="2"><p>参数</p></th>' in rendered
    assert extract_text(value).splitlines() == ["一次侧", "二次侧", "参数", "温度"]


def test_unknown_node_and_mark_are_preserved_with_safe_fallback():
    unknown = {
        "type": "futureCard",
        "attrs": {"source": "legacy", "payload": {"x": 1}},
        "content": [paragraph(text("仍可读取", {"type": "futureMark", "attrs": {"tone": "x"}}))],
    }
    value = document(unknown)

    validated = validate_document(value)

    assert {warning.code for warning in validated.warnings} == {"unknown_node", "unknown_mark"}
    assert validated.as_dict() == value
    rendered = render_document(validated)
    assert 'data-node-type="futureCard"' in rendered
    assert "仍可读取" in rendered
    assert extract_text(validated) == "仍可读取"


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ({"schema_version": 2, "doc": {"type": "doc"}}, "schema_version"),
        ({"schema_version": 1, "doc": {"type": "paragraph"}}, "document_root"),
        (document({"type": "heading", "attrs": {"level": 1}}), "heading_level"),
        (document({"type": "orderedList", "attrs": {"start": 0}}), "list_start"),
        (document({"type": "paragraph", "attrs": {"onclick": "x"}}), "node_attributes"),
        (document({"type": "text", "text": "x", "content": []}), "text_content"),
    ],
)
def test_invalid_documents_have_stable_error_codes(value, code):
    with pytest.raises(DocumentValidationError) as caught:
        validate_document(value)

    assert caught.value.code == code
    assert caught.value.path.startswith("$")


def test_document_depth_is_limited():
    node = paragraph(text("底部"))
    for _ in range(MAX_DOCUMENT_DEPTH + 1):
        node = {"type": "blockquote", "content": [node]}

    with pytest.raises(DocumentValidationError) as caught:
        validate_document(document(node))

    assert caught.value.code == "document_depth"


def test_document_json_must_not_contain_non_json_values():
    value = document(paragraph(text("x")))
    value["doc"]["attrs"] = {"bad": object()}

    with pytest.raises(DocumentValidationError) as caught:
        validate_document(value)

    assert caught.value.code == "json_type"


def test_document_attributes_reject_non_finite_numbers():
    value = document({"type": "futureCard", "attrs": {"weight": float("nan")}})

    with pytest.raises(DocumentValidationError) as caught:
        validate_document(value)

    assert caught.value.code == "attribute_number"
