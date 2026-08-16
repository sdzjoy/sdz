from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse


class TaxonomyTerm(models.Model):
    class Kind(models.TextChoices):
        SYSTEM = "system", "数据中心系统"
        TOPIC = "topic", "专业主题"
        DESIGN_STAGE = "design_stage", "设计阶段"
        USE_CASE = "use_case", "使用性质"

    kind = models.CharField("分类维度", max_length=20, choices=Kind.choices)
    name = models.CharField("名称", max_length=100)
    slug = models.SlugField("标识", max_length=100)
    description = models.CharField("说明", max_length=280, blank=True)
    sort_order = models.PositiveSmallIntegerField("排序", default=100)

    class Meta:
        ordering = ("kind", "sort_order", "name")
        verbose_name = "规范分类项"
        verbose_name_plural = "规范分类项"
        constraints = [
            models.UniqueConstraint(
                fields=("kind", "slug"),
                name="unique_standard_taxonomy_slug_per_kind",
            )
        ]

    def __str__(self):
        return f"{self.get_kind_display()} · {self.name}"


class Organization(models.Model):
    name = models.CharField("机构名称", max_length=200, unique=True)
    short_name = models.CharField("简称", max_length=80, blank=True)
    official_url = models.URLField("官方网站", blank=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "标准相关机构"
        verbose_name_plural = "标准相关机构"

    def __str__(self):
        return self.short_name or self.name


class Standard(models.Model):
    class Jurisdiction(models.TextChoices):
        DOMESTIC = "domestic", "国内设计依据"
        FOREIGN = "foreign", "国外技术参考"

    class Category(models.TextChoices):
        NATIONAL = "national", "国家标准"
        INDUSTRY = "industry", "行业标准"
        LOCAL = "local", "地方标准"
        GROUP = "group", "团体标准"
        INTERNATIONAL = "international", "国际标准"
        FOREIGN = "foreign", "外国标准"
        OTHER = "other", "其他"

    class Nature(models.TextChoices):
        MANDATORY = "mandatory", "强制性"
        RECOMMENDED = "recommended", "推荐性"
        GUIDANCE = "guidance", "指导性文件"
        UNKNOWN = "unknown", "未标明"

    class Status(models.TextChoices):
        DRAFT = "draft", "草案/未发布"
        UPCOMING = "upcoming", "即将实施"
        CURRENT = "current", "现行"
        WITHDRAWN = "withdrawn", "废止"
        SUPERSEDED = "superseded", "被替代"

    class UseLevel(models.TextChoices):
        REQUIRED = "required", "必须采用"
        RELATED = "related", "关联采用"
        REFERENCE = "reference", "参考使用"
        SCENARIO = "scenario", "特定场景使用"

    class VerificationState(models.TextChoices):
        UNVERIFIED = "unverified", "未核验"
        VERIFIED = "verified", "已核验"
        NEEDS_REVIEW = "needs_review", "需要复核"

    code = models.CharField("标准编号", max_length=80, unique=True, db_index=True)
    slug = models.SlugField("网址标识", max_length=140, unique=True)
    title_cn = models.CharField("中文名称", max_length=300)
    title_en = models.CharField("英文名称", max_length=400, blank=True)
    jurisdiction = models.CharField(
        "依据定位",
        max_length=12,
        choices=Jurisdiction.choices,
        default=Jurisdiction.DOMESTIC,
        db_index=True,
    )
    category = models.CharField("标准类别", max_length=16, choices=Category.choices, db_index=True)
    nature = models.CharField(
        "标准性质",
        max_length=16,
        choices=Nature.choices,
        default=Nature.UNKNOWN,
    )
    status = models.CharField(
        "状态", max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    use_level = models.CharField(
        "使用说明",
        max_length=16,
        choices=UseLevel.choices,
        default=UseLevel.REFERENCE,
    )
    country_region = models.CharField("国家或地区", max_length=100, default="中国")
    published_on = models.DateField("发布日期", null=True, blank=True)
    effective_on = models.DateField("实施日期", null=True, blank=True)
    withdrawn_on = models.DateField("废止日期", null=True, blank=True)
    ics_code = models.CharField("ICS 分类号", max_length=120, blank=True, db_index=True)
    ccs_code = models.CharField("CCS 分类号", max_length=120, blank=True, db_index=True)
    summary = models.TextField("适用范围与摘要", blank=True, max_length=3000)
    author_note = models.TextField("少惰主备注", blank=True, max_length=5000)
    taxonomies = models.ManyToManyField(
        TaxonomyTerm,
        verbose_name="专业分类",
        related_name="standards",
        blank=True,
    )
    organizations = models.ManyToManyField(
        Organization,
        through="StandardOrganization",
        related_name="standards",
        blank=True,
    )
    related_articles = models.ManyToManyField(
        "publishing.Article",
        verbose_name="相关文章",
        related_name="related_standards",
        blank=True,
        db_table="standards_standard_publishing_articles",
    )
    related_tools = models.ManyToManyField(
        "publishing.Tool",
        verbose_name="相关工具",
        related_name="related_standards",
        blank=True,
        db_table="standards_standard_publishing_tools",
    )
    verification_state = models.CharField(
        "核验状态",
        max_length=16,
        choices=VerificationState.choices,
        default=VerificationState.UNVERIFIED,
        db_index=True,
    )
    last_verified_at = models.DateTimeField("最后人工核验时间", null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="standards_verified",
        null=True,
        blank=True,
        verbose_name="最后核验人",
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        ordering = ("code",)
        verbose_name = "标准"
        verbose_name_plural = "标准"

    def __str__(self):
        return f"{self.code} {self.title_cn}"

    def save(self, *args, **kwargs):
        self.code = " ".join(self.code.strip().upper().split())
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("standards:standard_detail", args=(self.slug,))

    def clean(self):
        errors = {}
        if self.published_on and self.effective_on and self.effective_on < self.published_on:
            errors["effective_on"] = "实施日期不能早于发布日期。"
        baseline = self.effective_on or self.published_on
        if self.withdrawn_on and baseline and self.withdrawn_on < baseline:
            errors["withdrawn_on"] = "废止日期不能早于发布或实施日期。"
        if self.status == self.Status.DRAFT:
            if self.withdrawn_on:
                errors["withdrawn_on"] = "草案不能填写废止日期。"
        elif self.status in {self.Status.UPCOMING, self.Status.CURRENT}:
            if not self.effective_on:
                errors["effective_on"] = "即将实施或现行标准必须填写实施日期。"
            if self.withdrawn_on:
                errors["withdrawn_on"] = "即将实施或现行标准不能填写废止日期。"
        elif self.status in {self.Status.WITHDRAWN, self.Status.SUPERSEDED}:
            if not self.withdrawn_on:
                errors["withdrawn_on"] = "废止或被替代标准必须填写废止日期。"
        if self.verification_state == self.VerificationState.VERIFIED:
            if not self.last_verified_at or not self.verified_by_id:
                errors["verification_state"] = "已核验记录必须包含核验时间和核验人。"
            if self.pk and not self.evidence.exists():
                errors["verification_state"] = "至少添加一条来源证据后才能标记为已核验。"
        if errors:
            raise ValidationError(errors)


class StandardOrganization(models.Model):
    class Role(models.TextChoices):
        ISSUER = "issuer", "发布部门"
        JURISDICTION = "jurisdiction", "归口单位"
        SUPERVISOR = "supervisor", "主管部门"
        CHIEF_EDITOR = "chief_editor", "主编单位"
        PARTICIPANT = "participant", "参编单位"

    standard = models.ForeignKey(Standard, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    role = models.CharField("机构角色", max_length=20, choices=Role.choices)

    class Meta:
        ordering = ("role", "organization__name")
        verbose_name = "标准编制机构"
        verbose_name_plural = "标准编制机构"
        constraints = [
            models.UniqueConstraint(
                fields=("standard", "organization", "role"),
                name="unique_organization_role_per_standard",
            )
        ]

    def __str__(self):
        return f"{self.standard.code} · {self.get_role_display()} · {self.organization}"


class StandardRelation(models.Model):
    class RelationType(models.TextChoices):
        SUPERSEDES = "supersedes", "代替"
        RELATED = "related", "相关标准"

    source = models.ForeignKey(
        Standard,
        on_delete=models.CASCADE,
        related_name="outgoing_relations",
        verbose_name="当前标准",
    )
    target = models.ForeignKey(
        Standard,
        on_delete=models.PROTECT,
        related_name="incoming_relations",
        verbose_name="关联标准",
    )
    relation_type = models.CharField("关系", max_length=16, choices=RelationType.choices)
    note = models.CharField("关系说明", max_length=300, blank=True)

    class Meta:
        ordering = ("source__code", "relation_type", "target__code")
        verbose_name = "标准关系"
        verbose_name_plural = "标准关系"
        constraints = [
            models.UniqueConstraint(
                fields=("source", "target", "relation_type"),
                name="unique_relation_between_standards",
            ),
            models.CheckConstraint(
                condition=~models.Q(source=models.F("target")),
                name="standard_relation_cannot_reference_itself",
            ),
        ]

    def __str__(self):
        return f"{self.source.code} {self.get_relation_type_display()} {self.target.code}"

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def clean(self):
        if self.source_id == self.target_id:
            raise ValidationError({"target": "标准不能关联或代替自身。"})
        if self.relation_type != self.RelationType.SUPERSEDES:
            return

        frontier = {self.target_id}
        visited = set()
        while frontier:
            if self.source_id in frontier:
                raise ValidationError({"target": "该代替关系会形成循环。"})
            visited.update(frontier)
            relations = StandardRelation.objects.filter(
                relation_type=self.RelationType.SUPERSEDES,
                source_id__in=frontier,
            )
            if self.pk:
                relations = relations.exclude(pk=self.pk)
            frontier = set(relations.values_list("target_id", flat=True)) - visited


class SourceEvidence(models.Model):
    class SourceKind(models.TextChoices):
        OFFICIAL_PAGE = "official_page", "官方信息页"
        OFFICIAL_BULLETIN = "official_bulletin", "官方公告"
        OFFICIAL_CATALOG = "official_catalog", "官方目录"
        LEGAL_REFERENCE = "legal_reference", "合法辅助来源"

    standard = models.ForeignKey(
        Standard,
        on_delete=models.CASCADE,
        related_name="evidence",
        verbose_name="标准",
    )
    source_kind = models.CharField("来源类型", max_length=20, choices=SourceKind.choices)
    title = models.CharField("证据标题", max_length=300)
    url = models.URLField("来源网址", max_length=1000)
    publisher = models.CharField("发布机构", max_length=200, blank=True)
    excerpt = models.TextField("证据摘要", blank=True, max_length=2000)
    content_hash = models.CharField("内容摘要值", max_length=64, blank=True)
    is_primary = models.BooleanField("主要证据", default=False)
    captured_at = models.DateTimeField("采集时间", auto_now_add=True)
    verified_at = models.DateTimeField("人工核验时间", null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="standard_evidence_verified",
        null=True,
        blank=True,
        verbose_name="核验人",
    )

    class Meta:
        ordering = ("-is_primary", "-captured_at")
        verbose_name = "标准来源证据"
        verbose_name_plural = "标准来源证据"

    def __str__(self):
        return f"{self.standard.code} · {self.title}"


class StandardStatusHistory(models.Model):
    standard = models.ForeignKey(
        Standard,
        on_delete=models.CASCADE,
        related_name="status_history",
        verbose_name="标准",
    )
    from_status = models.CharField("原状态", max_length=16, choices=Standard.Status.choices)
    to_status = models.CharField("新状态", max_length=16, choices=Standard.Status.choices)
    effective_on = models.DateField("本次状态生效日期", null=True, blank=True)
    evidence = models.ForeignKey(
        SourceEvidence,
        on_delete=models.PROTECT,
        related_name="status_changes",
        verbose_name="依据证据",
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="standard_status_changes",
        verbose_name="操作人",
    )
    changed_at = models.DateTimeField("记录时间", auto_now_add=True)
    note = models.CharField("说明", max_length=500, blank=True)

    class Meta:
        ordering = ("-changed_at", "-pk")
        verbose_name = "标准状态历史"
        verbose_name_plural = "标准状态历史"
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(from_status=models.F("to_status")),
                name="standard_status_history_requires_change",
            )
        ]

    def __str__(self):
        return f"{self.standard.code}: {self.from_status} → {self.to_status}"


class PublicationBase(models.Model):
    title = models.CharField("名称", max_length=300)
    slug = models.SlugField("网址标识", max_length=140, unique=True)
    subtitle = models.CharField("副标题", max_length=300, blank=True)
    authors = models.CharField("作者或编者", max_length=400, blank=True)
    edition = models.CharField("版次", max_length=100, blank=True)
    publisher = models.CharField("出版社或发布机构", max_length=200, blank=True)
    published_on = models.DateField("出版日期", null=True, blank=True)
    isbn = models.CharField("ISBN", max_length=40, blank=True, db_index=True)
    summary = models.TextField("简介", blank=True, max_length=3000)
    version_notes = models.TextField("版本说明", blank=True, max_length=3000)
    official_url = models.URLField("官方或合法来源", max_length=1000, blank=True)
    legal_source_note = models.CharField("来源与版权说明", max_length=500, blank=True)
    taxonomies = models.ManyToManyField(
        TaxonomyTerm,
        verbose_name="适用主题",
        related_name="%(app_label)s_%(class)s_items",
        blank=True,
    )
    related_standards = models.ManyToManyField(
        Standard,
        verbose_name="相关标准",
        related_name="%(app_label)s_%(class)s_items",
        blank=True,
    )
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        abstract = True
        ordering = ("title",)

    def __str__(self):
        return self.title


class Manual(PublicationBase):
    series = models.CharField("系列或丛书", max_length=200, blank=True)
    organization = models.CharField("编制机构", max_length=300, blank=True)

    class Meta(PublicationBase.Meta):
        verbose_name = "技术手册"
        verbose_name_plural = "技术手册"

    def get_absolute_url(self):
        return reverse("standards:manual_detail", args=(self.slug,))


class ReferenceBook(PublicationBase):
    translators = models.CharField("译者", max_length=300, blank=True)

    class Meta(PublicationBase.Meta):
        verbose_name = "参考书"
        verbose_name_plural = "参考书"

    def get_absolute_url(self):
        return reverse("standards:book_detail", args=(self.slug,))


class MonitoringSource(models.Model):
    class FeedFormat(models.TextChoices):
        MANUAL_ONLY = "manual_only", "仅手工创建候选"
        SDZJOY_JSON = "sdzjoy_json", "受控 JSON 增量清单"

    name = models.CharField("来源名称", max_length=200)
    slug = models.SlugField("来源标识", max_length=100, unique=True)
    source_url = models.URLField("官方公告或目录地址", max_length=1000)
    feed_format = models.CharField(
        "检查方式",
        max_length=20,
        choices=FeedFormat.choices,
        default=FeedFormat.MANUAL_ONLY,
    )
    enabled = models.BooleanField("启用定时检查", default=False, db_index=True)
    automated_access_allowed = models.BooleanField("已确认允许自动访问", default=False)
    access_reviewed_at = models.DateTimeField("访问规则复核时间", null=True, blank=True)
    access_review_note = models.CharField("访问规则说明", max_length=500, blank=True)
    interval_days = models.PositiveSmallIntegerField(
        "检查间隔（天）",
        default=30,
        validators=(MinValueValidator(30),),
    )
    request_delay_seconds = models.PositiveSmallIntegerField(
        "单次请求间隔（秒）",
        default=3,
        validators=(MinValueValidator(1),),
    )
    timeout_seconds = models.PositiveSmallIntegerField(
        "请求超时（秒）",
        default=15,
        validators=(MinValueValidator(3),),
    )
    max_response_bytes = models.PositiveIntegerField(
        "最大响应字节数",
        default=1024 * 1024,
        validators=(MinValueValidator(1024),),
    )
    last_checked_at = models.DateTimeField("上次检查时间", null=True, blank=True)
    next_check_at = models.DateTimeField("下次允许检查时间", null=True, blank=True)
    next_allowed_at = models.DateTimeField("退避截止时间", null=True, blank=True)
    etag = models.CharField("ETag 缓存", max_length=300, blank=True)
    last_modified = models.CharField("Last-Modified 缓存", max_length=300, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "规范检查来源"
        verbose_name_plural = "规范检查来源"

    def __str__(self):
        return self.name

    def clean(self):
        errors = {}
        if self.enabled and self.feed_format == self.FeedFormat.MANUAL_ONLY:
            errors["enabled"] = "仅手工来源不能启用定时访问。"
        if self.enabled and not self.automated_access_allowed:
            errors["automated_access_allowed"] = "启用前必须确认该来源允许自动访问。"
        if self.automated_access_allowed and not self.access_reviewed_at:
            errors["access_reviewed_at"] = "确认自动访问时必须记录复核时间。"
        if errors:
            raise ValidationError(errors)


class CheckBatch(models.Model):
    class Trigger(models.TextChoices):
        MANUAL = "manual", "管理员手动"
        SCHEDULED = "scheduled", "月度计划"

    class Status(models.TextChoices):
        RUNNING = "running", "检查中"
        COMPLETED = "completed", "发现候选"
        NO_CHANGE = "no_change", "没有变化"
        RATE_LIMITED = "rate_limited", "来源限流"
        FAILED = "failed", "检查失败"

    source = models.ForeignKey(
        MonitoringSource,
        on_delete=models.PROTECT,
        related_name="batches",
        verbose_name="来源",
    )
    trigger = models.CharField("触发方式", max_length=12, choices=Trigger.choices)
    status = models.CharField(
        "批次状态",
        max_length=16,
        choices=Status.choices,
        default=Status.RUNNING,
        db_index=True,
    )
    started_at = models.DateTimeField("开始时间", auto_now_add=True)
    finished_at = models.DateTimeField("结束时间", null=True, blank=True)
    request_count = models.PositiveSmallIntegerField("请求次数", default=0)
    candidate_count = models.PositiveIntegerField("新增候选数", default=0)
    message = models.CharField("结果说明", max_length=1000, blank=True)

    class Meta:
        ordering = ("-started_at", "-pk")
        verbose_name = "规范检查批次"
        verbose_name_plural = "规范检查批次"
        constraints = [
            models.UniqueConstraint(
                fields=("source",),
                condition=models.Q(status="running"),
                name="one_running_check_batch_per_source",
            )
        ]

    def __str__(self):
        return f"{self.source} · {self.get_status_display()} · {self.started_at:%Y-%m-%d}"


class SourceSnapshot(models.Model):
    source = models.ForeignKey(
        MonitoringSource,
        on_delete=models.PROTECT,
        related_name="snapshots",
        verbose_name="来源",
    )
    batch = models.ForeignKey(
        CheckBatch,
        on_delete=models.PROTECT,
        related_name="snapshots",
        verbose_name="检查批次",
    )
    source_url = models.URLField("本次来源地址", max_length=1000)
    response_status = models.PositiveSmallIntegerField("响应状态")
    etag = models.CharField("ETag", max_length=300, blank=True)
    last_modified = models.CharField("Last-Modified", max_length=300, blank=True)
    content_hash = models.CharField("响应摘要值", max_length=64, db_index=True)
    payload = models.JSONField("受控增量数据", default=dict)
    captured_at = models.DateTimeField("快照时间", auto_now_add=True)

    class Meta:
        ordering = ("-captured_at", "-pk")
        verbose_name = "来源证据快照"
        verbose_name_plural = "来源证据快照"

    def __str__(self):
        return f"{self.source} · {self.content_hash[:12]}"


class CandidateChange(models.Model):
    class ChangeType(models.TextChoices):
        NEW_STANDARD = "new_standard", "新增标准"
        STATUS = "status", "状态或日期变化"
        METADATA = "metadata", "基础信息变化"

    class ReviewState(models.TextChoices):
        PENDING = "pending", "待审核"
        APPROVED = "approved", "已通过"
        REJECTED = "rejected", "已拒绝"

    source = models.ForeignKey(
        MonitoringSource,
        on_delete=models.PROTECT,
        related_name="candidates",
        verbose_name="来源",
    )
    snapshot = models.ForeignKey(
        SourceSnapshot,
        on_delete=models.PROTECT,
        related_name="candidates",
        null=True,
        blank=True,
        verbose_name="证据快照",
    )
    standard = models.ForeignKey(
        Standard,
        on_delete=models.PROTECT,
        related_name="candidate_changes",
        null=True,
        blank=True,
        verbose_name="对应标准",
    )
    external_key = models.CharField("来源条目标识", max_length=200)
    fingerprint = models.CharField("候选幂等摘要", max_length=64, blank=True)
    change_type = models.CharField("变化类型", max_length=20, choices=ChangeType.choices)
    proposed_data = models.JSONField("建议数据", default=dict)
    differences = models.JSONField("差异摘要", default=dict)
    evidence_title = models.CharField("证据标题", max_length=300)
    evidence_url = models.URLField("证据网址", max_length=1000)
    state = models.CharField(
        "审核状态",
        max_length=12,
        choices=ReviewState.choices,
        default=ReviewState.PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField("发现时间", auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "规范候选变更"
        verbose_name_plural = "规范候选变更"
        constraints = [
            models.UniqueConstraint(
                fields=("source", "fingerprint"),
                name="unique_candidate_fingerprint_per_source",
            )
        ]

    def __str__(self):
        target = self.standard.code if self.standard_id else self.external_key
        return f"{target} · {self.get_change_type_display()}"


class CandidateReview(models.Model):
    class Decision(models.TextChoices):
        APPROVE = "approve", "通过"
        REJECT = "reject", "拒绝"

    candidate = models.OneToOneField(
        CandidateChange,
        on_delete=models.PROTECT,
        related_name="review",
        verbose_name="候选变更",
    )
    decision = models.CharField("审核决定", max_length=8, choices=Decision.choices)
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="standard_candidate_reviews",
        verbose_name="审核人",
    )
    note = models.CharField("审核说明", max_length=1000, blank=True)
    reviewed_at = models.DateTimeField("审核时间", auto_now_add=True)
    status_history = models.ForeignKey(
        StandardStatusHistory,
        on_delete=models.PROTECT,
        related_name="candidate_reviews",
        null=True,
        blank=True,
        verbose_name="产生的状态历史",
    )

    class Meta:
        ordering = ("-reviewed_at", "-pk")
        verbose_name = "规范候选审核"
        verbose_name_plural = "规范候选审核"

    def __str__(self):
        return f"{self.candidate} · {self.get_decision_display()}"
