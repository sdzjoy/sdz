import math
import re
from datetime import date

from django.db import models
from django.utils.functional import cached_property
from django.utils.html import strip_tags
from modelcluster.fields import ParentalManyToManyField
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.fields import StreamField
from wagtail.models import Page
from wagtail.search import index
from wagtail.snippets.models import register_snippet

from .blocks import BODY_BLOCKS

CJK_CHARACTER_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
LATIN_WORD_RE = re.compile(r"\b[A-Za-z0-9][A-Za-z0-9'-]*\b")


def _stream_text(value):
    """Yield readable text from StreamField values without loading linked files."""
    if value is None:
        return
    if isinstance(value, str):
        yield strip_tags(value)
        return
    if hasattr(value, "source") and isinstance(value.source, str):
        yield strip_tags(value.source)
        return
    if hasattr(value, "items"):
        for key, child in value.items():
            if key != "editor_note":
                yield from _stream_text(child)
        return
    if isinstance(value, (list, tuple)) or hasattr(value, "__iter__"):
        try:
            for child in value:
                yield from _stream_text(getattr(child, "value", child))
        except TypeError:
            return


@register_snippet
class Topic(models.Model):
    name = models.CharField("名称", max_length=80, unique=True)
    slug = models.SlugField("标识", max_length=80, unique=True)
    description = models.CharField("说明", max_length=240, blank=True)
    accent = models.CharField("标记颜色", max_length=7, default="#52d5c3")

    panels = [
        FieldPanel("name"),
        FieldPanel("slug"),
        FieldPanel("description"),
        FieldPanel("accent"),
    ]

    class Meta:
        ordering = ("name",)
        verbose_name = "主题"
        verbose_name_plural = "主题"

    def __str__(self):
        return self.name


class ProjectIndexPage(Page):
    intro = models.CharField("栏目说明", max_length=240, blank=True)

    max_count = 1
    parent_page_types = ["core.HomePage"]
    subpage_types = ["content.ProjectPage"]
    content_panels = Page.content_panels + [FieldPanel("intro")]

    class Meta:
        verbose_name = "项目栏目"

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["projects"] = (
            self.get_children().live().public().specific().order_by("-first_published_at")
        )
        return context


class ProjectPage(Page):
    class Status(models.TextChoices):
        ACTIVE = "active", "进行中"
        COMPLETE = "complete", "已完成"
        MAINTAINED = "maintained", "持续维护"
        ARCHIVED = "archived", "已归档"

    summary = models.CharField("摘要", max_length=280)
    status = models.CharField(
        "状态", max_length=12, choices=Status.choices, default=Status.ACTIVE
    )
    started_on = models.DateField("开始日期", default=date.today)
    completed_on = models.DateField("完成日期", null=True, blank=True)
    featured = models.BooleanField("首页推荐", default=False)
    body = StreamField(BODY_BLOCKS, verbose_name="正文", blank=True, use_json_field=True)
    topics = ParentalManyToManyField(Topic, verbose_name="主题", blank=True)

    parent_page_types = ["content.ProjectIndexPage"]
    subpage_types = []
    content_panels = Page.content_panels + [
        FieldPanel("summary"),
        FieldPanel("status"),
        FieldPanel("started_on"),
        FieldPanel("completed_on"),
        FieldPanel("featured"),
        FieldPanel("topics"),
        FieldPanel("body"),
    ]
    search_fields = Page.search_fields + [
        index.SearchField("summary", boost=2),
        index.SearchField("body"),
    ]

    class Meta:
        verbose_name = "项目"

    @property
    def timeline(self):
        items = []
        for kind, queryset in (
            ("article", self.article_pages.live().public()),
            ("note", self.note_pages.live().public()),
            ("tool", self.tool_pages.live().public()),
        ):
            for page in queryset:
                items.append(
                    {"kind": kind, "date": page.timeline_date, "page": page}
                )
        return sorted(
            items,
            key=lambda item: (item["date"], item["page"].pk),
            reverse=True,
        )


class ArticleIndexPage(Page):
    intro = models.CharField("栏目说明", max_length=240, blank=True)

    max_count = 1
    parent_page_types = ["core.HomePage"]
    subpage_types = ["content.ArticlePage"]
    content_panels = Page.content_panels + [FieldPanel("intro")]

    class Meta:
        verbose_name = "文章栏目"

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["articles"] = (
            self.get_children().live().public().specific().order_by("-first_published_at")
        )
        return context


class ArticlePage(Page):
    summary = models.CharField("摘要", max_length=280)
    published_on = models.DateField("文章日期", default=date.today)
    reading_minutes = models.PositiveSmallIntegerField(
        "阅读分钟（人工覆盖）",
        null=True,
        blank=True,
        help_text="留空时根据正文自动估算。",
    )
    featured = models.BooleanField("首页推荐", default=False)
    cover_image = models.ForeignKey(
        "wagtailimages.Image",
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
        verbose_name="封面图",
    )
    project = models.ForeignKey(
        ProjectPage,
        on_delete=models.PROTECT,
        related_name="article_pages",
        null=True,
        blank=True,
        verbose_name="所属项目",
    )
    topics = ParentalManyToManyField(Topic, verbose_name="主题", blank=True)
    body = StreamField(BODY_BLOCKS, verbose_name="正文", blank=True, use_json_field=True)

    parent_page_types = ["content.ArticleIndexPage"]
    subpage_types = []
    content_panels = Page.content_panels + [
        FieldPanel("summary"),
        FieldPanel("cover_image"),
        FieldPanel("body"),
    ]
    settings_panels = [
        MultiFieldPanel(
            [
                FieldPanel("published_on"),
                FieldPanel("project"),
                FieldPanel("topics"),
                FieldPanel("featured"),
                FieldPanel("reading_minutes"),
            ],
            heading="文章资料",
        ),
        *Page.settings_panels,
    ]
    search_fields = Page.search_fields + [
        index.SearchField("summary", boost=2),
        index.SearchField("body"),
    ]

    class Meta:
        verbose_name = "文章"

    @property
    def timeline_date(self):
        return self.published_on

    @cached_property
    def estimated_reading_minutes(self):
        text = " ".join(part for part in _stream_text(self.body) if part)
        chinese_characters = len(CJK_CHARACTER_RE.findall(text))
        latin_words = len(LATIN_WORD_RE.findall(text))
        return max(1, math.ceil(chinese_characters / 350 + latin_words / 180))

    @property
    def effective_reading_minutes(self):
        return self.reading_minutes or self.estimated_reading_minutes

    @cached_property
    def reference_entries(self):
        """Return article references, merging repeated sources and cited locations."""
        references = {}
        for block in self.body:
            if block.block_type != "reference":
                continue
            value = dict(block.value)
            key = (
                str(value.get("identifier") or "").strip().casefold(),
                str(value.get("edition") or "").strip().casefold(),
                str(value.get("title_zh") or "").strip().casefold(),
            )
            if key not in references:
                value.pop("editor_note", None)
                value["clauses"] = []
                value["page_ranges"] = []
                references[key] = value
            reference = references[key]
            clause = str(value.get("clause") or "").strip()
            pages = str(value.get("pages") or "").strip()
            if clause and clause not in reference["clauses"]:
                reference["clauses"].append(clause)
            if pages and pages not in reference["page_ranges"]:
                reference["page_ranges"].append(pages)
        return list(references.values())


class NoteIndexPage(Page):
    intro = models.CharField("栏目说明", max_length=240, blank=True)

    max_count = 1
    parent_page_types = ["core.HomePage"]
    subpage_types = ["content.NotePage"]
    content_panels = Page.content_panels + [FieldPanel("intro")]

    class Meta:
        verbose_name = "随记栏目"

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["notes"] = (
            self.get_children().live().public().specific().order_by("-first_published_at")
        )
        return context


class NotePage(Page):
    summary = models.CharField("摘要", max_length=280)
    noted_on = models.DateField("记录日期", default=date.today)
    project = models.ForeignKey(
        ProjectPage,
        on_delete=models.PROTECT,
        related_name="note_pages",
        null=True,
        blank=True,
        verbose_name="所属项目",
    )
    promoted_article = models.ForeignKey(
        ArticlePage,
        on_delete=models.PROTECT,
        related_name="source_notes",
        null=True,
        blank=True,
        verbose_name="整理后的文章",
    )
    topics = ParentalManyToManyField(Topic, verbose_name="主题", blank=True)
    body = StreamField(BODY_BLOCKS, verbose_name="正文", blank=True, use_json_field=True)

    parent_page_types = ["content.NoteIndexPage"]
    subpage_types = []
    content_panels = Page.content_panels + [
        FieldPanel("summary"),
        FieldPanel("noted_on"),
        FieldPanel("project"),
        FieldPanel("promoted_article"),
        FieldPanel("topics"),
        FieldPanel("body"),
    ]
    search_fields = Page.search_fields + [
        index.SearchField("summary", boost=2),
        index.SearchField("body"),
    ]

    class Meta:
        verbose_name = "随记"

    @property
    def timeline_date(self):
        return self.noted_on


class ToolIndexPage(Page):
    intro = models.CharField("栏目说明", max_length=240, blank=True)

    max_count = 1
    parent_page_types = ["core.HomePage"]
    subpage_types = ["content.ToolPage"]
    content_panels = Page.content_panels + [FieldPanel("intro")]

    class Meta:
        verbose_name = "工具栏目"

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["tools"] = (
            self.get_children().live().public().specific().order_by("-first_published_at")
        )
        return context


class ToolPage(Page):
    class Status(models.TextChoices):
        ONLINE = "online", "在线"
        BETA = "beta", "测试中"
        MAINTENANCE = "maintenance", "维护中"
        RETIRED = "retired", "已下线"

    summary = models.CharField("摘要", max_length=280)
    launched_on = models.DateField("上线日期", default=date.today)
    status = models.CharField(
        "状态", max_length=16, choices=Status.choices, default=Status.ONLINE
    )
    service_url = models.URLField("工具地址", blank=True)
    source_url = models.URLField("源代码地址", blank=True)
    featured = models.BooleanField("首页推荐", default=False)
    project = models.ForeignKey(
        ProjectPage,
        on_delete=models.PROTECT,
        related_name="tool_pages",
        null=True,
        blank=True,
        verbose_name="所属项目",
    )
    topics = ParentalManyToManyField(Topic, verbose_name="主题", blank=True)
    body = StreamField(BODY_BLOCKS, verbose_name="正文", blank=True, use_json_field=True)

    parent_page_types = ["content.ToolIndexPage"]
    subpage_types = []
    content_panels = Page.content_panels + [
        FieldPanel("summary"),
        FieldPanel("launched_on"),
        FieldPanel("status"),
        FieldPanel("service_url"),
        FieldPanel("source_url"),
        FieldPanel("featured"),
        FieldPanel("project"),
        FieldPanel("topics"),
        FieldPanel("body"),
    ]
    search_fields = Page.search_fields + [
        index.SearchField("summary", boost=2),
        index.SearchField("body"),
    ]

    class Meta:
        verbose_name = "工具"

    @property
    def timeline_date(self):
        return self.launched_on


class AboutPage(Page):
    intro = models.CharField("简介", max_length=280)
    body = StreamField(BODY_BLOCKS, verbose_name="正文", blank=True, use_json_field=True)

    max_count = 1
    parent_page_types = ["core.HomePage"]
    subpage_types = []
    content_panels = Page.content_panels + [FieldPanel("intro"), FieldPanel("body")]
    search_fields = Page.search_fields + [
        index.SearchField("intro", boost=2),
        index.SearchField("body"),
    ]

    class Meta:
        verbose_name = "关于"
