from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse


def _web_url_has_credentials_or_unsafe_scheme(value):
    if not value:
        return False
    parsed = urlsplit(value)
    return parsed.scheme not in {"http", "https"} or bool(parsed.username or parsed.password)


class ResourceQuerySet(models.QuerySet):
    def visible_to(self, user):
        allowed = [Resource.AccessLevel.PUBLIC]
        if user is not None and user.is_authenticated and user.is_active:
            rank = {
                "L0": 0,
                "L1": 1,
                "L2": 2,
                "L3": 3,
            }.get(user.membership_level, 0)
            allowed = [
                level
                for level, required_rank in (
                    (Resource.AccessLevel.PUBLIC, 0),
                    (Resource.AccessLevel.MEMBER, 1),
                    (Resource.AccessLevel.ADVANCED, 2),
                    (Resource.AccessLevel.OWNER, 3),
                )
                if required_rank <= rank
            ]
        return self.filter(status=Resource.Status.PUBLISHED, access_level__in=allowed)


class Resource(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        PUBLISHED = "published", "已发布"
        ARCHIVED = "archived", "已归档"

    class AccessLevel(models.TextChoices):
        PUBLIC = "L0", "公开区"
        MEMBER = "L1", "普通会员区"
        ADVANCED = "L2", "高级会员区"
        OWNER = "L3", "站长私人区"

    class CopyrightStatus(models.TextChoices):
        SELF_MADE = "self_made", "自制"
        OPEN_SOURCE = "open_source", "开源许可"
        OFFICIAL_FREE = "official_free", "官方免费"
        AUTHORIZED = "authorized", "已获授权"
        METADATA_ONLY = "metadata_only", "仅目录与合法来源"
        RESTRICTED = "restricted", "受版权限制"
        UNKNOWN = "unknown", "尚待确认"

    title = models.CharField("资源名称", max_length=300)
    slug = models.SlugField("网址标识", max_length=160, unique=True)
    summary = models.TextField("简介", max_length=5000)
    screenshot = models.ImageField(
        "预览图",
        upload_to="resources/screenshots/%Y/%m/",
        blank=True,
    )
    screenshot_alt = models.CharField("预览图说明", max_length=200, blank=True)
    author = models.CharField("作者或制作人", max_length=300, blank=True)
    source_name = models.CharField("来源名称", max_length=300, blank=True)
    source_url = models.URLField("来源网址", max_length=1000, blank=True)
    file_format = models.CharField("主要格式", max_length=120, blank=True)
    size_bytes = models.PositiveBigIntegerField("大小（字节）", null=True, blank=True)
    checksum_algorithm = models.CharField("校验算法", max_length=20, blank=True)
    checksum_value = models.CharField("校验值", max_length=256, blank=True)
    copyright_status = models.CharField(
        "版权状态",
        max_length=20,
        choices=CopyrightStatus.choices,
        default=CopyrightStatus.UNKNOWN,
        db_index=True,
    )
    copyright_note = models.TextField("版权与使用说明", max_length=2000, blank=True)
    access_level = models.CharField(
        "访问等级",
        max_length=2,
        choices=AccessLevel.choices,
        default=AccessLevel.PUBLIC,
        db_index=True,
    )
    status = models.CharField(
        "发布状态",
        max_length=12,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    taxonomies = models.ManyToManyField(
        "standards.TaxonomyTerm",
        verbose_name="适用主题",
        related_name="resources",
        blank=True,
    )
    related_standards = models.ManyToManyField(
        "standards.Standard",
        verbose_name="相关标准",
        related_name="related_resources",
        blank=True,
    )
    related_manuals = models.ManyToManyField(
        "standards.Manual",
        verbose_name="相关手册",
        related_name="related_resources",
        blank=True,
    )
    related_books = models.ManyToManyField(
        "standards.ReferenceBook",
        verbose_name="相关参考书",
        related_name="related_resources",
        blank=True,
    )
    published_at = models.DateTimeField("发布时间", null=True, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    objects = ResourceQuerySet.as_manager()

    class Meta:
        ordering = ("title",)
        verbose_name = "资源"
        verbose_name_plural = "资源"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("resources:resource_detail", args=(self.slug,))

    def clean(self):
        errors = {}
        if self.status == self.Status.PUBLISHED and not self.published_at:
            errors["published_at"] = "发布资源必须记录发布时间。"
        if self.checksum_value and not self.checksum_algorithm:
            errors["checksum_algorithm"] = "填写校验值时必须注明算法。"
        if _web_url_has_credentials_or_unsafe_scheme(self.source_url):
            errors["source_url"] = "来源网址只能使用无账号凭据的 HTTP(S) 地址。"
        if errors:
            raise ValidationError(errors)


class ResourceVersion(models.Model):
    resource = models.ForeignKey(
        Resource,
        on_delete=models.CASCADE,
        related_name="versions",
        verbose_name="资源",
    )
    version = models.CharField("版本", max_length=120)
    released_on = models.DateField("版本日期", null=True, blank=True)
    change_notes = models.TextField("版本说明", max_length=3000, blank=True)
    filename = models.CharField("文件名", max_length=300, blank=True)
    file_format = models.CharField("格式", max_length=120, blank=True)
    size_bytes = models.PositiveBigIntegerField("大小（字节）", null=True, blank=True)
    checksum_algorithm = models.CharField("校验算法", max_length=20, blank=True)
    checksum_value = models.CharField("校验值", max_length=256, blank=True)
    is_current = models.BooleanField("当前版本", default=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        ordering = ("-is_current", "-released_on", "-pk")
        verbose_name = "资源版本"
        verbose_name_plural = "资源版本"
        constraints = [
            models.UniqueConstraint(
                fields=("resource", "version"),
                name="unique_version_per_resource",
            ),
            models.UniqueConstraint(
                fields=("resource",),
                condition=models.Q(is_current=True),
                name="one_current_version_per_resource",
            ),
        ]

    def __str__(self):
        return f"{self.resource} · {self.version}"

    def clean(self):
        if self.checksum_value and not self.checksum_algorithm:
            raise ValidationError({"checksum_algorithm": "填写校验值时必须注明算法。"})


class ResourceMirror(models.Model):
    class Provider(models.TextChoices):
        BAIDU = "baidu", "百度网盘"
        ALIYUN = "aliyun", "阿里云盘"
        CLOUD_115 = "115", "115 网盘"
        PCLOUD = "pcloud", "pCloud"
        QUARK = "quark", "夸克网盘"
        OFFICIAL = "official", "官方或原站"
        OTHER = "other", "其他"

    class Status(models.TextChoices):
        ACTIVE = "active", "可用"
        HIDDEN = "hidden", "已隐藏"
        FAILED = "failed", "已失效"
        REPLACED = "replaced", "已更换"

    resource = models.ForeignKey(
        Resource,
        on_delete=models.CASCADE,
        related_name="mirrors",
        verbose_name="资源",
    )
    provider = models.CharField("网盘或入口", max_length=16, choices=Provider.choices)
    label = models.CharField("入口名称", max_length=120, blank=True)
    share_url = models.URLField("分享链接", max_length=1500)
    extraction_code = models.CharField("提取码", max_length=80, blank=True)
    status = models.CharField(
        "入口状态",
        max_length=12,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    replaced_by = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="replaces",
        null=True,
        blank=True,
        verbose_name="替换入口",
    )
    failure_note = models.CharField("失效或隐藏说明", max_length=500, blank=True)
    last_verified_at = models.DateTimeField("最后验证时间", null=True, blank=True)
    last_verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="resource_mirrors_verified",
        null=True,
        blank=True,
        verbose_name="最后验证人",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        ordering = ("provider", "pk")
        verbose_name = "资源网盘入口"
        verbose_name_plural = "资源网盘入口"

    def __str__(self):
        return f"{self.resource} · {self.get_provider_display()} · {self.get_status_display()}"

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def clean(self):
        errors = {}
        if self.replaced_by_id == self.pk and self.pk:
            errors["replaced_by"] = "入口不能替换为自身。"
        if self.status == self.Status.REPLACED and not self.replaced_by_id:
            errors["replaced_by"] = "标记为已更换时必须选择替换入口。"
        if self.replaced_by_id and self.replaced_by.resource_id != self.resource_id:
            errors["replaced_by"] = "替换入口必须属于同一资源。"
        if _web_url_has_credentials_or_unsafe_scheme(self.share_url):
            errors["share_url"] = "分享链接只能使用无账号凭据的 HTTP(S) 地址。"
        if errors:
            raise ValidationError(errors)


class ResourceIssue(models.Model):
    class IssueType(models.TextChoices):
        UNAVAILABLE = "unavailable", "入口失效"
        WRONG_CODE = "wrong_code", "提取码错误"
        WRONG_METADATA = "wrong_metadata", "信息有误"
        COPYRIGHT = "copyright", "版权问题"
        OTHER = "other", "其他"

    class Status(models.TextChoices):
        OPEN = "open", "待处理"
        RESOLVED = "resolved", "已处理"
        REJECTED = "rejected", "不成立"

    resource = models.ForeignKey(
        Resource,
        on_delete=models.CASCADE,
        related_name="issues",
        verbose_name="资源",
    )
    mirror = models.ForeignKey(
        ResourceMirror,
        on_delete=models.SET_NULL,
        related_name="issues",
        null=True,
        blank=True,
        verbose_name="相关入口",
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="resource_issues",
        verbose_name="反馈人",
    )
    issue_type = models.CharField("问题类型", max_length=20, choices=IssueType.choices)
    details = models.TextField("问题说明", max_length=1500, blank=True)
    status = models.CharField(
        "处理状态",
        max_length=12,
        choices=Status.choices,
        default=Status.OPEN,
        db_index=True,
    )
    created_at = models.DateTimeField("反馈时间", auto_now_add=True)
    resolved_at = models.DateTimeField("处理时间", null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="resource_issues_resolved",
        null=True,
        blank=True,
        verbose_name="处理人",
    )
    resolution_note = models.CharField("处理说明", max_length=1000, blank=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "资源失效或纠错反馈"
        verbose_name_plural = "资源失效或纠错反馈"

    def __str__(self):
        return f"{self.resource} · {self.get_issue_type_display()}"

    def clean(self):
        if self.mirror_id and self.mirror.resource_id != self.resource_id:
            raise ValidationError({"mirror": "入口必须属于所选资源。"})


class ImportBatch(models.Model):
    class State(models.TextChoices):
        READY = "ready", "校验通过，待确认"
        INVALID = "invalid", "存在错误"
        CONFIRMED = "confirmed", "已确认发布"
        FAILED = "failed", "文件解析失败"

    filename = models.CharField("文件名", max_length=255)
    file_type = models.CharField("文件类型", max_length=8)
    file_hash = models.CharField("文件摘要值", max_length=64)
    state = models.CharField("导入状态", max_length=12, choices=State.choices, db_index=True)
    row_count = models.PositiveIntegerField("数据行数", default=0)
    error_count = models.PositiveIntegerField("错误行数", default=0)
    error_message = models.CharField("文件错误", max_length=1000, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="resource_imports_created",
        verbose_name="创建人",
    )
    created_at = models.DateTimeField("预览时间", auto_now_add=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="resource_imports_confirmed",
        null=True,
        blank=True,
        verbose_name="确认人",
    )
    confirmed_at = models.DateTimeField("确认时间", null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "资源批量导入"
        verbose_name_plural = "资源批量导入"

    def __str__(self):
        return f"{self.filename} · {self.get_state_display()}"


class ImportRow(models.Model):
    class State(models.TextChoices):
        VALID = "valid", "校验通过"
        INVALID = "invalid", "存在错误"
        IMPORTED = "imported", "已发布"

    batch = models.ForeignKey(
        ImportBatch,
        on_delete=models.CASCADE,
        related_name="rows",
        verbose_name="导入批次",
    )
    row_number = models.PositiveIntegerField("原文件行号")
    raw_data = models.JSONField("原始行", default=dict)
    normalized_data = models.JSONField("标准化预览", default=dict)
    errors = models.JSONField("校验错误", default=list)
    state = models.CharField("行状态", max_length=10, choices=State.choices)
    created_resource = models.OneToOneField(
        Resource,
        on_delete=models.PROTECT,
        related_name="import_row",
        null=True,
        blank=True,
        verbose_name="已创建资源",
    )

    class Meta:
        ordering = ("row_number",)
        verbose_name = "资源导入预览行"
        verbose_name_plural = "资源导入预览行"
        constraints = [
            models.UniqueConstraint(
                fields=("batch", "row_number"),
                name="unique_row_number_per_resource_import",
            )
        ]

    def __str__(self):
        return f"{self.batch.filename} · 第 {self.row_number} 行 · {self.get_state_display()}"
