import math
import re
from datetime import date

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.validators import RegexValidator
from django.db import models
from django.utils.functional import cached_property

from .documents import empty_document, extract_text, render_document, validate_document
from .managers import ContentManager

CJK_CHARACTER_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
LATIN_WORD_RE = re.compile(r"\b[A-Za-z0-9][A-Za-z0-9'-]*\b")
ACCENT_VALIDATOR = RegexValidator(
    regex=r"^#[0-9A-Fa-f]{6}$",
    message="颜色必须是六位十六进制值，例如 #C8623A。",
)


class Topic(models.Model):
    legacy_source_id = models.PositiveBigIntegerField(
        "旧系统标识",
        null=True,
        blank=True,
        unique=True,
        editable=False,
    )
    name = models.CharField("名称", max_length=80, unique=True)
    slug = models.SlugField("标识", max_length=80, unique=True, allow_unicode=True)
    description = models.CharField("说明", max_length=240, blank=True)
    accent = models.CharField(
        "标记颜色",
        max_length=7,
        default="#C8623A",
        validators=(ACCENT_VALIDATOR,),
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "主题"
        verbose_name_plural = "主题"

    def __str__(self):
        return self.name


class Asset(models.Model):
    class Kind(models.TextChoices):
        IMAGE = "image", "图片"
        ATTACHMENT = "attachment", "普通附件"

    kind = models.CharField("类型", max_length=12, choices=Kind.choices)
    legacy_source_id = models.PositiveBigIntegerField(
        "旧系统标识",
        null=True,
        blank=True,
        unique=True,
        editable=False,
    )
    file = models.FileField("文件", upload_to="assets/%Y/%m/", max_length=500)
    original_name = models.CharField("原文件名", max_length=255)
    title = models.CharField("素材名称", max_length=200, blank=True)
    alt_text = models.CharField("替代文字", max_length=300, blank=True)
    mime_type = models.CharField("MIME 类型", max_length=100)
    byte_size = models.PositiveBigIntegerField("文件大小", default=0)
    width = models.PositiveIntegerField("宽度", null=True, blank=True)
    height = models.PositiveIntegerField("高度", null=True, blank=True)
    sha256 = models.CharField("SHA-256", max_length=64, blank=True, db_index=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="publishing_assets_uploaded",
        verbose_name="上传人",
    )
    created_at = models.DateTimeField("上传时间", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)
    deleted_at = models.DateTimeField("移入回收站时间", null=True, blank=True, db_index=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "素材"
        verbose_name_plural = "素材"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(byte_size__gte=0),
                name="publishing_asset_non_negative_size",
            )
        ]

    def __str__(self):
        return self.title or self.original_name


class SiteProfile(models.Model):
    singleton = models.BooleanField(default=True, unique=True, editable=False)
    site_name = models.CharField("网站名称", max_length=120, default="少惰主 · SDZJOY")
    tagline = models.CharField("网站简介", max_length=240, blank=True)
    owner_name = models.CharField("站长称呼", max_length=80, default="少惰主")
    article_intro = models.CharField("文章栏目说明", max_length=240, blank=True)
    project_intro = models.CharField("项目栏目说明", max_length=240, blank=True)
    note_intro = models.CharField("随记栏目说明", max_length=240, blank=True)
    tool_intro = models.CharField("工具栏目说明", max_length=240, blank=True)
    about_intro = models.CharField("关于页简介", max_length=280, blank=True)
    about_body_json = models.JSONField("关于页正文 JSON", default=empty_document)
    about_rendered_html = models.TextField("关于页正文 HTML", blank=True)
    about_body_text = models.TextField("关于页纯文本", blank=True)
    default_cover = models.ForeignKey(
        Asset,
        on_delete=models.SET_NULL,
        related_name="site_profiles_as_default_cover",
        null=True,
        blank=True,
        verbose_name="默认封面",
    )
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "网站设置"
        verbose_name_plural = "网站设置"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(singleton=True),
                name="publishing_site_profile_is_singleton",
            )
        ]

    def __str__(self):
        return self.site_name

    def save(self, *args, **kwargs):
        validated = validate_document(self.about_body_json)
        self.about_body_json = validated.as_dict()
        self.about_rendered_html = render_document(validated)
        self.about_body_text = extract_text(validated)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | {
                "about_body_json",
                "about_rendered_html",
                "about_body_text",
            }
        super().save(*args, **kwargs)


class ContentEntry(models.Model):
    class Kind(models.TextChoices):
        ARTICLE = "article", "文章"
        PROJECT = "project", "项目"
        NOTE = "note", "随记"
        TOOL = "tool", "工具"

    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        PUBLISHED = "published", "已发布"

    kind = models.CharField("内容类型", max_length=12, choices=Kind.choices, db_index=True)
    legacy_source_id = models.PositiveBigIntegerField(
        "旧系统标识",
        null=True,
        blank=True,
        unique=True,
        editable=False,
    )
    title = models.CharField("标题", max_length=200)
    slug = models.SlugField("网址标识", max_length=160, allow_unicode=True)
    summary = models.CharField("摘要", max_length=500, blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="publishing_content_authored",
        verbose_name="作者",
    )
    topics = models.ManyToManyField(Topic, related_name="content_entries", blank=True)
    cover_asset = models.ForeignKey(
        Asset,
        on_delete=models.SET_NULL,
        related_name="content_entries_as_cover",
        null=True,
        blank=True,
        verbose_name="封面",
    )
    featured = models.BooleanField("首页推荐", default=False, db_index=True)
    body_json = models.JSONField("编辑正文 JSON", default=empty_document)
    rendered_html = models.TextField("编辑正文 HTML", blank=True)
    body_text = models.TextField("编辑正文纯文本", blank=True)
    published_body_json = models.JSONField("线上正文 JSON", null=True, blank=True)
    published_rendered_html = models.TextField("线上正文 HTML", blank=True)
    published_body_text = models.TextField("线上正文纯文本", blank=True)
    published_title = models.CharField("线上标题", max_length=200, blank=True)
    published_slug = models.SlugField(
        "线上网址标识",
        max_length=160,
        allow_unicode=True,
        blank=True,
    )
    published_summary = models.CharField("线上摘要", max_length=500, blank=True)
    published_featured = models.BooleanField("线上首页推荐", default=False)
    published_cover_asset = models.ForeignKey(
        Asset,
        on_delete=models.SET_NULL,
        related_name="content_entries_as_published_cover",
        null=True,
        blank=True,
        verbose_name="线上封面",
    )
    published_topics = models.ManyToManyField(
        Topic,
        related_name="published_content_entries",
        blank=True,
        verbose_name="线上主题",
    )
    published_metadata = models.JSONField("线上类型资料", default=dict, blank=True)
    status = models.CharField(
        "发布状态",
        max_length=12,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    published_at = models.DateTimeField("首次发布时间", null=True, blank=True, db_index=True)
    version = models.PositiveBigIntegerField("编辑版本", default=0)
    created_at = models.DateTimeField("创建时间", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True, db_index=True)
    deleted_at = models.DateTimeField("移入回收站时间", null=True, blank=True, db_index=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="publishing_content_deleted",
        null=True,
        blank=True,
        verbose_name="删除人",
    )

    objects = ContentManager()

    class Meta:
        ordering = ("-updated_at", "-pk")
        verbose_name = "内容"
        verbose_name_plural = "内容"
        constraints = [
            models.UniqueConstraint(
                fields=("kind", "slug"),
                name="publishing_unique_slug_per_kind",
            ),
            models.UniqueConstraint(
                fields=("kind", "published_slug"),
                condition=~models.Q(published_slug=""),
                name="publishing_unique_published_slug_per_kind",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=0),
                name="publishing_content_non_negative_version",
            ),
            models.CheckConstraint(
                condition=models.Q(status="draft") | models.Q(published_at__isnull=False),
                name="publishing_published_content_has_timestamp",
            ),
            models.CheckConstraint(
                condition=models.Q(status="draft") | ~models.Q(published_slug=""),
                name="publishing_published_content_has_slug",
            ),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        validated = validate_document(self.body_json)
        self.body_json = validated.as_dict()
        self.rendered_html = render_document(validated)
        self.body_text = extract_text(validated)

        document_fields = {"body_json", "rendered_html", "body_text"}
        if self.published_body_json is not None:
            published = validate_document(self.published_body_json)
            self.published_body_json = published.as_dict()
            self.published_rendered_html = render_document(published)
            self.published_body_text = extract_text(published)
            document_fields |= {
                "published_body_json",
                "published_rendered_html",
                "published_body_text",
            }
        else:
            self.published_rendered_html = ""
            self.published_body_text = ""

        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | document_fields
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        prefixes = {
            self.Kind.ARTICLE: "articles",
            self.Kind.PROJECT: "projects",
            self.Kind.NOTE: "notes",
            self.Kind.TOOL: "tools",
        }
        slug = (
            self.published_slug
            if self.status == self.Status.PUBLISHED and self.published_slug
            else self.slug
        )
        return f"/{prefixes[self.kind]}/{slug}/"

    @property
    def specific(self):
        if self.kind not in self.Kind.values:
            return self
        try:
            return getattr(self, self.kind)
        except ObjectDoesNotExist:
            return self

    @property
    def is_in_trash(self):
        return self.deleted_at is not None


class Project(ContentEntry):
    class ProjectStatus(models.TextChoices):
        ACTIVE = "active", "进行中"
        COMPLETE = "complete", "已完成"
        MAINTAINED = "maintained", "持续维护"
        ARCHIVED = "archived", "已归档"

    project_status = models.CharField(
        "项目状态",
        max_length=12,
        choices=ProjectStatus.choices,
        default=ProjectStatus.ACTIVE,
    )
    started_on = models.DateField("开始日期", default=date.today)
    completed_on = models.DateField("完成日期", null=True, blank=True)

    class Meta:
        verbose_name = "项目"
        verbose_name_plural = "项目"

    def save(self, *args, **kwargs):
        self.kind = self.Kind.PROJECT
        super().save(*args, **kwargs)


class Article(ContentEntry):
    published_on = models.DateField("文章日期", default=date.today)
    reading_minutes = models.PositiveSmallIntegerField(
        "阅读分钟（人工覆盖）",
        null=True,
        blank=True,
    )
    parent_project = models.ForeignKey(
        Project,
        on_delete=models.PROTECT,
        related_name="articles",
        null=True,
        blank=True,
        verbose_name="所属项目",
    )

    class Meta:
        verbose_name = "文章"
        verbose_name_plural = "文章"

    def save(self, *args, **kwargs):
        self.kind = self.Kind.ARTICLE
        super().save(*args, **kwargs)

    @cached_property
    def estimated_reading_minutes(self):
        chinese_characters = len(CJK_CHARACTER_RE.findall(self.body_text))
        latin_words = len(LATIN_WORD_RE.findall(self.body_text))
        return max(1, math.ceil(chinese_characters / 350 + latin_words / 180))

    @property
    def effective_reading_minutes(self):
        return self.reading_minutes or self.estimated_reading_minutes


class Note(ContentEntry):
    noted_on = models.DateField("记录日期", default=date.today)
    parent_project = models.ForeignKey(
        Project,
        on_delete=models.PROTECT,
        related_name="notes",
        null=True,
        blank=True,
        verbose_name="所属项目",
    )
    promoted_article = models.ForeignKey(
        Article,
        on_delete=models.PROTECT,
        related_name="source_notes",
        null=True,
        blank=True,
        verbose_name="整理后的文章",
    )

    class Meta:
        verbose_name = "随记"
        verbose_name_plural = "随记"

    def save(self, *args, **kwargs):
        self.kind = self.Kind.NOTE
        super().save(*args, **kwargs)


class Tool(ContentEntry):
    class ToolStatus(models.TextChoices):
        ONLINE = "online", "在线"
        BETA = "beta", "测试中"
        MAINTENANCE = "maintenance", "维护中"
        RETIRED = "retired", "已下线"

    launched_on = models.DateField("上线日期", default=date.today)
    tool_status = models.CharField(
        "工具状态",
        max_length=16,
        choices=ToolStatus.choices,
        default=ToolStatus.ONLINE,
    )
    service_url = models.URLField("工具地址", max_length=1000, blank=True)
    source_url = models.URLField("源代码地址", max_length=1000, blank=True)
    parent_project = models.ForeignKey(
        Project,
        on_delete=models.PROTECT,
        related_name="tools",
        null=True,
        blank=True,
        verbose_name="所属项目",
    )

    class Meta:
        verbose_name = "工具"
        verbose_name_plural = "工具"

    def save(self, *args, **kwargs):
        self.kind = self.Kind.TOOL
        super().save(*args, **kwargs)


class ContentRevision(models.Model):
    class Action(models.TextChoices):
        SAVE = "save", "手工保存前"
        PUBLISH = "publish", "发布前"
        RESTORE = "restore", "恢复前"
        UNPUBLISH = "unpublish", "取消发布前"
        DELETE = "delete", "移入回收站前"
        TRASH_RESTORE = "trash_restore", "移出回收站前"

    content = models.ForeignKey(
        ContentEntry,
        on_delete=models.CASCADE,
        related_name="revisions",
        verbose_name="内容",
    )
    number = models.PositiveBigIntegerField("版本号")
    action = models.CharField("动作", max_length=16, choices=Action.choices)
    snapshot = models.JSONField("版本快照")
    summary = models.CharField("修改摘要", max_length=240, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="publishing_revisions_created",
        null=True,
        blank=True,
        verbose_name="操作人",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-number", "-pk")
        verbose_name = "内容版本"
        verbose_name_plural = "内容版本"
        constraints = [
            models.UniqueConstraint(
                fields=("content", "number"),
                name="publishing_unique_revision_number",
            ),
            models.CheckConstraint(
                condition=models.Q(number__gte=1),
                name="publishing_revision_positive_number",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    action__in=(
                        "save",
                        "publish",
                        "restore",
                        "unpublish",
                        "delete",
                        "trash_restore",
                    )
                ),
                name="publishing_revision_valid_action",
            ),
        ]

    def __str__(self):
        return f"{self.content} · v{self.number}"
