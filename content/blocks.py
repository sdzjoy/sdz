from wagtail import blocks
from wagtail.contrib.table_block.blocks import TableBlock
from wagtail.documents.blocks import DocumentChooserBlock
from wagtail.images.blocks import ImageChooserBlock

RICH_TEXT_FEATURES = [
    "bold",
    "italic",
    "code",
    "superscript",
    "subscript",
    "strikethrough",
    "link",
    "ol",
    "ul",
    "hr",
    "blockquote",
]

TABLE_OPTIONS = {
    "minSpareRows": 0,
    "startRows": 3,
    "startCols": 3,
    "colHeaders": False,
    "rowHeaders": False,
    "contextMenu": True,
    "editor": "text",
    "stretchH": "all",
    "height": 216,
}


class SectionHeadingBlock(blocks.StructBlock):
    level = blocks.ChoiceBlock(
        label="层级",
        choices=(("h2", "二级标题"), ("h3", "三级标题"), ("h4", "四级标题")),
        default="h2",
    )
    text = blocks.CharBlock(label="标题", max_length=140)

    class Meta:
        icon = "title"
        label = "章节标题"
        group = "文字内容"
        template = "content/blocks/section_heading_block.html"


class CalloutBlock(blocks.StructBlock):
    kind = blocks.ChoiceBlock(
        label="类型",
        choices=(
            ("info", "说明"),
            ("tip", "提示"),
            ("note", "注意"),
            ("warning", "警告"),
            ("experience", "工程经验"),
        ),
        default="info",
    )
    title = blocks.CharBlock(label="标题", required=False, max_length=100)
    content = blocks.RichTextBlock(label="内容", features=RICH_TEXT_FEATURES)

    class Meta:
        icon = "warning"
        label = "提示框"
        group = "文字内容"
        template = "content/blocks/callout_block.html"


class EquationVariableBlock(blocks.StructBlock):
    symbol = blocks.CharBlock(label="变量", max_length=60)
    meaning = blocks.CharBlock(label="含义", max_length=160)
    unit = blocks.CharBlock(label="单位", required=False, max_length=60)


class EquationBlock(blocks.StructBlock):
    latex = blocks.TextBlock(
        label="LaTeX 源码",
        help_text=r"例如：Q = c_p m \Delta T。无需输入 $$。",
    )
    number = blocks.CharBlock(label="公式编号", required=False, max_length=40)
    caption = blocks.CharBlock(label="说明", required=False, max_length=200)
    variables = blocks.ListBlock(
        EquationVariableBlock(), label="变量说明", required=False
    )

    class Meta:
        icon = "code"
        label = "工程公式"
        group = "工程资料"
        template = "content/blocks/equation_block.html"
        form_classname = "struct-block editorial-equation-block"


class ReferenceBlock(blocks.StructBlock):
    kind = blocks.ChoiceBlock(
        label="资料类型",
        choices=(
            ("standard", "标准规范"),
            ("manual", "手册/参考书"),
            ("paper", "论文"),
            ("web", "网页"),
            ("other", "其他资料"),
        ),
        default="standard",
    )
    identifier = blocks.CharBlock(label="标准号或编号", required=False, max_length=120)
    title_zh = blocks.CharBlock(label="中文名", max_length=240)
    title_en = blocks.CharBlock(label="英文名", required=False, max_length=300)
    edition = blocks.CharBlock(label="年份或版本", required=False, max_length=80)
    clause = blocks.CharBlock(label="条文号", required=False, max_length=120)
    pages = blocks.CharBlock(label="页码", required=False, max_length=80)
    excerpt = blocks.TextBlock(label="引用摘要", required=False)
    organization = blocks.CharBlock(label="来源机构", required=False, max_length=180)
    source_url = blocks.URLBlock(label="来源链接", required=False)
    accessed_on = blocks.DateBlock(label="查阅日期", required=False)
    editor_note = blocks.TextBlock(
        label="编辑备注",
        required=False,
        help_text="仅作为编辑资料保存；前台不显示。",
    )

    class Meta:
        icon = "doc-full"
        label = "规范与资料引用"
        group = "工程资料"
        template = "content/blocks/reference_block.html"

    def get_context(self, value, parent_context=None):
        context = super().get_context(value, parent_context=parent_context)
        context["kind_label"] = dict(self.child_blocks["kind"].field.choices).get(
            value.get("kind"), "资料"
        )
        return context


class CaptionedImageBlock(blocks.StructBlock):
    image = ImageChooserBlock(label="图片")
    alt_text = blocks.CharBlock(
        label="替代文字",
        required=False,
        max_length=240,
        help_text="用于无障碍阅读；留空时使用图片库中的说明。",
    )
    caption = blocks.CharBlock(label="图注", required=False, max_length=300)
    source = blocks.CharBlock(label="来源/版权", required=False, max_length=240)
    width = blocks.ChoiceBlock(
        label="显示宽度",
        choices=(("normal", "正文宽度"), ("wide", "加宽"), ("full", "通栏")),
        default="normal",
    )

    class Meta:
        icon = "image"
        label = "图片与图注"
        group = "媒体附件"
        template = "content/blocks/captioned_image_block.html"


class DataTableBlock(blocks.StructBlock):
    title = blocks.CharBlock(label="表题", required=False, max_length=200)
    table = TableBlock(label="表格数据", table_options=TABLE_OPTIONS)
    units = blocks.CharBlock(label="单位说明", required=False, max_length=120)
    source = blocks.CharBlock(label="数据来源", required=False, max_length=240)
    notes = blocks.TextBlock(label="表下注释", required=False)

    class Meta:
        icon = "table"
        label = "数据表格"
        group = "工程资料"
        template = "content/blocks/data_table_block.html"


class ParameterItemBlock(blocks.StructBlock):
    name = blocks.CharBlock(label="参数名", max_length=100)
    value = blocks.CharBlock(label="数值", max_length=100)
    unit = blocks.CharBlock(label="单位", required=False, max_length=40)
    note = blocks.CharBlock(label="说明", required=False, max_length=160)


class ParameterCardBlock(blocks.StructBlock):
    title = blocks.CharBlock(label="标题", required=False, max_length=120)
    items = blocks.ListBlock(ParameterItemBlock(), label="参数", min_num=1)

    class Meta:
        icon = "list-ul"
        label = "参数卡片"
        group = "工程资料"
        template = "content/blocks/parameter_card_block.html"


class AttachmentBlock(blocks.StructBlock):
    document = DocumentChooserBlock(label="文件")
    display_name = blocks.CharBlock(label="显示名称", required=False, max_length=180)
    version = blocks.CharBlock(label="版本", required=False, max_length=80)
    description = blocks.CharBlock(label="说明", required=False, max_length=240)

    class Meta:
        icon = "doc-full"
        label = "文件附件"
        group = "媒体附件"
        template = "content/blocks/attachment_block.html"


class ExternalResourceBlock(blocks.StructBlock):
    title = blocks.CharBlock(label="资料名称", max_length=180)
    url = blocks.URLBlock(label="外部链接")
    provider = blocks.CharBlock(label="平台/来源", required=False, max_length=80)
    version = blocks.CharBlock(label="版本", required=False, max_length=80)
    description = blocks.CharBlock(label="说明", required=False, max_length=240)

    class Meta:
        icon = "link"
        label = "外部资料链接"
        group = "媒体附件"
        template = "content/blocks/external_resource_block.html"


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
    show_line_numbers = blocks.BooleanBlock(
        label="显示行号", required=False, default=False
    )

    class Meta:
        icon = "code"
        label = "代码块"
        group = "技术内容"
        template = "content/blocks/code_block.html"


BODY_BLOCKS = [
    (
        "heading",
        blocks.CharBlock(
            label="小标题（旧版）",
            max_length=140,
            form_classname="title",
            template="content/blocks/heading_block.html",
            group="文字内容",
        ),
    ),
    ("section_heading", SectionHeadingBlock()),
    (
        "paragraph",
        blocks.RichTextBlock(
            label="正文段落", features=RICH_TEXT_FEATURES, group="文字内容"
        ),
    ),
    (
        "markdown",
        blocks.TextBlock(
            label="Markdown",
            help_text="原始 HTML 会被禁用并在输出时再次净化。",
            template="content/blocks/markdown_block.html",
            group="技术内容",
        ),
    ),
    (
        "divider",
        blocks.StaticBlock(
            label="分隔线",
            icon="horizontalrule",
            group="文字内容",
            template="content/blocks/divider_block.html",
        ),
    ),
    ("callout", CalloutBlock()),
    ("equation", EquationBlock()),
    ("reference", ReferenceBlock()),
    ("captioned_image", CaptionedImageBlock()),
    ("data_table", DataTableBlock()),
    ("parameter_card", ParameterCardBlock()),
    ("attachment", AttachmentBlock()),
    ("external_resource", ExternalResourceBlock()),
    ("code", CodeBlock()),
    (
        "image",
        ImageChooserBlock(
            label="图片（旧版）",
            template="content/blocks/image_block.html",
            group="媒体附件",
        ),
    ),
    (
        "table",
        TableBlock(
            label="表格（旧版）", table_options=TABLE_OPTIONS, group="工程资料"
        ),
    ),
]
