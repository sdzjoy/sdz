from unittest.mock import patch

import pytest
from django.template import Context, Template
from wagtail.blocks import StreamBlock

from content.blocks import BODY_BLOCKS
from content.templatetags.content_tags import render_latex_mathml

pytestmark = pytest.mark.django_db


def body_block_map():
    return dict(BODY_BLOCKS)


def test_existing_block_names_remain_available_for_old_streamfield_json():
    blocks = body_block_map()

    assert {"heading", "paragraph", "markdown", "code", "image", "table"} <= blocks.keys()

    stream = StreamBlock(BODY_BLOCKS)
    value = stream.to_python(
        [
            {"type": "heading", "value": "旧文章标题", "id": "old-heading"},
            {"type": "markdown", "value": "旧文章正文", "id": "old-markdown"},
            {
                "type": "code",
                "value": {"language": "python", "code": "print('old')", "caption": ""},
                "id": "old-code",
            },
        ]
    )

    assert [child.block_type for child in value] == ["heading", "markdown", "code"]
    assert value[2].value["show_line_numbers"] is False


def test_professional_blocks_are_grouped_and_available():
    blocks = body_block_map()

    assert {
        "section_heading",
        "divider",
        "callout",
        "equation",
        "reference",
        "captioned_image",
        "data_table",
        "parameter_card",
        "attachment",
        "external_resource",
    } <= blocks.keys()
    assert blocks["equation"].meta.group == "工程资料"
    assert blocks["captioned_image"].meta.group == "媒体附件"
    assert blocks["code"].meta.group == "技术内容"


def test_table_blocks_use_the_bundled_handsontable_locale():
    blocks = body_block_map()

    assert blocks["data_table"].child_blocks["table"].table_options["language"] == "en-US"
    assert blocks["table"].table_options["language"] == "en-US"


def test_equation_block_renders_self_hosted_mathml_and_metadata():
    equation = body_block_map()["equation"]
    value = equation.to_python(
        {
            "latex": r"Q = c_p m \Delta T",
            "number": "3-1",
            "caption": "冷量平衡式",
            "variables": [
                {"symbol": "Q", "meaning": "冷量", "unit": "kW"},
                {"symbol": "m", "meaning": "质量流量", "unit": "kg/s"},
            ],
        }
    )

    rendered = equation.render(value)

    assert "<math" in rendered
    assert 'display="block"' in rendered
    assert "冷量平衡式" in rendered
    assert "(3-1)" in rendered
    assert "质量流量" in rendered
    assert "cdn" not in rendered.lower()


def test_formula_failure_preserves_escaped_source_instead_of_raising():
    with patch(
        "content.templatetags.content_tags.latex_converter.convert",
        side_effect=ValueError("bad formula"),
    ):
        rendered = str(render_latex_mathml(r"x <script>alert(1)</script>"))

    assert "公式暂时无法渲染" in rendered
    assert "&lt;script&gt;" in rendered
    assert "<script>" not in rendered


def test_formula_length_limit_uses_safe_fallback():
    rendered = str(render_latex_mathml("x" * 10001))

    assert "公式过长" in rendered
    assert "<math" not in rendered


def test_reference_and_parameter_templates_escape_user_html():
    blocks = body_block_map()
    reference = blocks["reference"]
    reference_html = reference.render(
        reference.to_python(
            {
                "kind": "standard",
                "identifier": "GB 50000",
                "title_zh": "<script>alert(1)</script>",
                "title_en": "",
                "edition": "2026",
                "clause": "3.1.1",
                "pages": "",
                "excerpt": "引用摘要",
                "organization": "",
                "source_url": "https://example.com/reference",
                "accessed_on": None,
                "editor_note": "",
            }
        )
    )
    parameter = blocks["parameter_card"]
    parameter_html = parameter.render(
        parameter.to_python(
            {
                "title": "设计参数",
                "items": [
                    {
                        "name": "送风温度",
                        "value": "<img src=x onerror=alert(1)>",
                        "unit": "℃",
                        "note": "",
                    }
                ],
            }
        )
    )

    assert "<script>" not in reference_html
    assert "&lt;script&gt;" in reference_html
    assert "<img" not in parameter_html
    assert "&lt;img" in parameter_html


def test_mathml_filter_can_be_used_from_django_templates():
    template = Template("{% load content_tags %}{{ formula|render_latex_mathml }}")

    rendered = template.render(Context({"formula": r"\frac{1}{2}"}))

    assert "<math" in rendered
