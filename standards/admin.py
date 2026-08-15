from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError

from .models import (
    CandidateChange,
    CandidateReview,
    CheckBatch,
    Manual,
    MonitoringSource,
    Organization,
    ReferenceBook,
    SourceEvidence,
    SourceSnapshot,
    Standard,
    StandardOrganization,
    StandardRelation,
    StandardStatusHistory,
    TaxonomyTerm,
)
from .monitoring import candidate_fingerprint, run_source_check
from .reviews import approve_candidate, reject_candidate
from .services import change_standard_status, mark_standard_verified


class StandardOrganizationInline(admin.TabularInline):
    model = StandardOrganization
    extra = 0


class StandardRelationInline(admin.TabularInline):
    model = StandardRelation
    fk_name = "source"
    extra = 0


class SourceEvidenceInline(admin.StackedInline):
    model = SourceEvidence
    extra = 0
    readonly_fields = ("captured_at", "verified_at", "verified_by")


class StandardAdminForm(forms.ModelForm):
    class Meta:
        model = Standard
        fields = (
            "code",
            "slug",
            "title_cn",
            "title_en",
            "jurisdiction",
            "category",
            "nature",
            "status",
            "use_level",
            "country_region",
            "published_on",
            "effective_on",
            "withdrawn_on",
            "ics_code",
            "ccs_code",
            "summary",
            "author_note",
            "taxonomies",
            "related_articles",
            "related_tools",
            "verification_state",
            "last_verified_at",
            "verified_by",
        )

    def clean_status(self):
        status = self.cleaned_data["status"]
        if self.instance.pk:
            original = Standard.objects.only("status").get(pk=self.instance.pk)
            if status != original.status and not self.instance.evidence.exists():
                raise forms.ValidationError("请先保存一条来源证据，再修改标准状态。")
        return status


@admin.action(description="使用主要来源证据标记为已核验")
def verify_selected_standards(modeladmin, request, queryset):
    verified = 0
    skipped = []
    for standard in queryset:
        evidence = standard.evidence.order_by("-is_primary", "-captured_at").first()
        if evidence is None:
            skipped.append(standard.code)
            continue
        try:
            mark_standard_verified(
                standard=standard,
                evidence=evidence,
                actor=request.user,
            )
        except ValidationError as exc:
            skipped.append(f"{standard.code}（{exc}）")
        else:
            verified += 1
    if verified:
        modeladmin.message_user(request, f"已核验 {verified} 条标准。", messages.SUCCESS)
    if skipped:
        modeladmin.message_user(
            request,
            "以下记录没有可用来源证据，未核验：" + "、".join(skipped),
            messages.WARNING,
        )


@admin.register(Standard)
class StandardAdmin(admin.ModelAdmin):
    form = StandardAdminForm
    list_display = (
        "code",
        "title_cn",
        "jurisdiction",
        "category",
        "status",
        "verification_state",
        "last_verified_at",
    )
    list_filter = (
        "jurisdiction",
        "category",
        "nature",
        "status",
        "verification_state",
        "taxonomies",
    )
    search_fields = ("code", "title_cn", "title_en", "ics_code", "ccs_code")
    prepopulated_fields = {"slug": ("code",)}
    filter_horizontal = ("taxonomies", "related_articles", "related_tools")
    readonly_fields = ("verification_state", "last_verified_at", "verified_by")
    inlines = (StandardOrganizationInline, StandardRelationInline, SourceEvidenceInline)
    actions = (verify_selected_standards,)
    fieldsets = (
        (
            "基础信息",
            {
                "fields": (
                    "code",
                    "slug",
                    "title_cn",
                    "title_en",
                    "jurisdiction",
                    "country_region",
                    "category",
                    "nature",
                    "use_level",
                )
            },
        ),
        (
            "生命周期",
            {"fields": ("status", "published_on", "effective_on", "withdrawn_on")},
        ),
        ("分类", {"fields": ("ics_code", "ccs_code", "taxonomies")}),
        ("说明与关联", {"fields": ("summary", "author_note", "related_articles", "related_tools")}),
        (
            "核验记录（请通过列表动作更新）",
            {"fields": ("verification_state", "last_verified_at", "verified_by")},
        ),
    )

    def save_model(self, request, obj, form, change):
        requested_status = obj.status
        original_status = None
        if change:
            original_status = Standard.objects.only("status").get(pk=obj.pk).status
            obj.status = original_status
        super().save_model(request, obj, form, change)
        if original_status and requested_status != original_status:
            evidence = obj.evidence.order_by("-is_primary", "-captured_at").first()
            if evidence is None:
                self.message_user(
                    request,
                    "状态未变更：请先保存一条来源证据，再修改标准状态。",
                    messages.ERROR,
                )
                return
            change_standard_status(
                standard=obj,
                to_status=requested_status,
                evidence=evidence,
                actor=request.user,
                note="管理员通过标准后台调整。",
            )


@admin.register(TaxonomyTerm)
class TaxonomyTermAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "slug", "sort_order")
    list_filter = ("kind",)
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "short_name", "official_url")
    search_fields = ("name", "short_name")


@admin.register(SourceEvidence)
class SourceEvidenceAdmin(admin.ModelAdmin):
    list_display = ("standard", "title", "source_kind", "is_primary", "captured_at")
    list_filter = ("source_kind", "is_primary", "captured_at")
    search_fields = ("standard__code", "standard__title_cn", "title", "publisher")
    readonly_fields = ("captured_at", "verified_at", "verified_by")


@admin.register(StandardRelation)
class StandardRelationAdmin(admin.ModelAdmin):
    list_display = ("source", "relation_type", "target")
    list_filter = ("relation_type",)
    search_fields = ("source__code", "target__code", "source__title_cn", "target__title_cn")


@admin.register(StandardStatusHistory)
class StandardStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("standard", "from_status", "to_status", "changed_by", "changed_at")
    list_filter = ("from_status", "to_status", "changed_at")
    search_fields = ("standard__code", "standard__title_cn", "note")
    readonly_fields = (
        "standard",
        "from_status",
        "to_status",
        "effective_on",
        "evidence",
        "changed_by",
        "changed_at",
        "note",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class PublicationAdmin(admin.ModelAdmin):
    list_display = ("title", "authors", "publisher", "published_on")
    list_filter = ("published_on", "taxonomies")
    search_fields = ("title", "subtitle", "authors", "publisher", "isbn")
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ("taxonomies", "related_standards")


admin.site.register(Manual, PublicationAdmin)
admin.site.register(ReferenceBook, PublicationAdmin)


@admin.action(description="立即检查选中的允许来源")
def check_selected_sources(modeladmin, request, queryset):
    for source in queryset:
        try:
            batch = run_source_check(source=source)
        except ValidationError as exc:
            modeladmin.message_user(request, f"{source}：{exc}", messages.ERROR)
        else:
            modeladmin.message_user(
                request,
                f"{source}：{batch.get_status_display()}，{batch.message}",
                messages.SUCCESS if batch.status != CheckBatch.Status.FAILED else messages.WARNING,
            )


@admin.register(MonitoringSource)
class MonitoringSourceAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "feed_format",
        "enabled",
        "automated_access_allowed",
        "last_checked_at",
        "next_check_at",
    )
    list_filter = ("feed_format", "enabled", "automated_access_allowed")
    search_fields = ("name", "source_url", "access_review_note")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = (
        "last_checked_at",
        "next_check_at",
        "next_allowed_at",
        "etag",
        "last_modified",
    )
    actions = (check_selected_sources,)


class ReadOnlyMonitoringAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CheckBatch)
class CheckBatchAdmin(ReadOnlyMonitoringAdmin):
    list_display = (
        "source",
        "trigger",
        "status",
        "request_count",
        "candidate_count",
        "started_at",
    )
    list_filter = ("trigger", "status", "started_at")
    search_fields = ("source__name", "message")
    readonly_fields = (
        "source",
        "trigger",
        "status",
        "started_at",
        "finished_at",
        "request_count",
        "candidate_count",
        "message",
    )


@admin.register(SourceSnapshot)
class SourceSnapshotAdmin(ReadOnlyMonitoringAdmin):
    list_display = ("source", "response_status", "content_hash", "captured_at")
    list_filter = ("response_status", "captured_at")
    search_fields = ("source__name", "content_hash")
    readonly_fields = (
        "source",
        "batch",
        "source_url",
        "response_status",
        "etag",
        "last_modified",
        "content_hash",
        "payload",
        "captured_at",
    )


@admin.action(description="审核通过选中的候选")
def approve_selected_candidates(modeladmin, request, queryset):
    approved = 0
    for candidate in queryset:
        try:
            approve_candidate(candidate=candidate, actor=request.user, note="管理员批量审核通过。")
        except (ValidationError, PermissionDenied) as exc:
            modeladmin.message_user(request, f"{candidate}：{exc}", messages.ERROR)
        else:
            approved += 1
    if approved:
        modeladmin.message_user(request, f"已通过 {approved} 条候选。", messages.SUCCESS)


@admin.action(description="拒绝选中的候选")
def reject_selected_candidates(modeladmin, request, queryset):
    rejected = 0
    for candidate in queryset:
        try:
            reject_candidate(candidate=candidate, actor=request.user, note="管理员批量拒绝。")
        except (ValidationError, PermissionDenied) as exc:
            modeladmin.message_user(request, f"{candidate}：{exc}", messages.ERROR)
        else:
            rejected += 1
    if rejected:
        modeladmin.message_user(request, f"已拒绝 {rejected} 条候选。", messages.SUCCESS)


@admin.register(CandidateChange)
class CandidateChangeAdmin(admin.ModelAdmin):
    list_display = (
        "external_key",
        "change_type",
        "standard",
        "source",
        "state",
        "created_at",
    )
    list_filter = ("change_type", "state", "source", "created_at")
    search_fields = ("external_key", "standard__code", "standard__title_cn")
    readonly_fields = ("fingerprint", "state", "snapshot", "created_at")
    actions = (approve_selected_candidates, reject_selected_candidates)

    def save_model(self, request, obj, form, change):
        obj.fingerprint = candidate_fingerprint(
            external_key=obj.external_key,
            change_type=obj.change_type,
            proposed_data=obj.proposed_data,
        )
        super().save_model(request, obj, form, change)

    def has_change_permission(self, request, obj=None):
        if obj and obj.state != CandidateChange.ReviewState.PENDING:
            return False
        return super().has_change_permission(request, obj)


@admin.register(CandidateReview)
class CandidateReviewAdmin(ReadOnlyMonitoringAdmin):
    list_display = ("candidate", "decision", "reviewer", "reviewed_at")
    list_filter = ("decision", "reviewed_at")
    search_fields = ("candidate__external_key", "reviewer__email", "note")
    readonly_fields = (
        "candidate",
        "decision",
        "reviewer",
        "note",
        "reviewed_at",
        "status_history",
    )
