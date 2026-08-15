from wagtail import blocks
from wagtail.contrib.table_block.blocks import TableBlock
from wagtail.images.blocks import ImageChooserBlock


class CodeBlock(blocks.StructBlock):
    language = blocks.ChoiceBlock(
        label="语言",
        choices=(
            ("text", "纯文本"),
            ("bash", "Shell / Bash"),
            ("powershell", "PowerShell"),
            ("python", "Python"),
            ("javascript", "JavaScript"),
            ("json", "JSON"),
            ("yaml", "YAML"),
            ("nginx", "Nginx"),
        ),
        default="text",
    )
    code = blocks.TextBlock(label="代码")
    caption = blocks.CharBlock(label="说明", required=False, max_length=160)

    class Meta:
        icon = "code"
        label = "代码块"
        template = "content/blocks/code_block.html"


BODY_BLOCKS = [
    (
        "heading",
        blocks.CharBlock(
            label="小标题",
            max_length=140,
            form_classname="title",
            template="content/blocks/heading_block.html",
        ),
    ),
    (
        "paragraph",
        blocks.RichTextBlock(
            label="富文本",
            features=[
                "bold",
                "italic",
                "link",
                "ol",
                "ul",
                "hr",
                "blockquote",
            ],
        ),
    ),
    (
        "markdown",
        blocks.TextBlock(
            label="Markdown",
            help_text="原始 HTML 会被禁用并在输出时再次净化。",
            template="content/blocks/markdown_block.html",
        ),
    ),
    ("code", CodeBlock()),
    (
        "image",
        ImageChooserBlock(
            label="图片",
            template="content/blocks/image_block.html",
        ),
    ),
    (
        "table",
        TableBlock(
            label="表格",
            table_options={
                "minSpareRows": 0,
                "startRows": 3,
                "startCols": 3,
                "colHeaders": False,
                "rowHeaders": False,
                "contextMenu": True,
                "editor": "text",
                "stretchH": "all",
                "height": 216,
            },
        ),
    ),
]
