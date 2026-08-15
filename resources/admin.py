from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters

from .imports import confirm_import, preview_import
from .models import (
    ImportBatch,
    ImportRow,
    Resource,
    ResourceIssue,
    ResourceMirror,
    ResourceVersion,
)


class ResourceVersionInline(admin.TabularInline):
    model = ResourceVersion
    extra = 0


class ResourceMirrorInline(admin.StackedInline):
    model = ResourceMirror
    extra = 0
    readonly_fields = ("last_verified_at", "last_verified_by", "created_at", "updated_at")


class ResourceAdminForm(forms.ModelForm):
    class Meta:
        model = Resource
        fields = (
            "title",
            "slug",
            "summary",
            "screenshot",
            "screenshot_alt",
            "author",
            "source_name",
            "source_url",
            "file_format",
            "size_bytes",
            "checksum_algorithm",
            "checksum_value",
            "copyright_status",
            "copyright_note",
            "access_level",
            "status",
            "taxonomies",
            "related_standards",
            "related_manuals",
            "related_books",
            "published_at",
        )

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("status") == Resource.Status.PUBLISHED:
            self.instance.published_at = self.instance.published_at or timezone.now()
        return cleaned_data


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    form = ResourceAdminForm
    list_display = (
        "title",
        "access_level",
        "copyright_status",
        "status",
        "published_at",
    )
    list_filter = ("access_level", "copyright_status", "status", "taxonomies")
    search_fields = ("title", "summary", "author", "source_name", "file_format")
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = (
        "taxonomies",
        "related_standards",
        "related_manuals",
        "related_books",
    )
    inlines = (ResourceVersionInline, ResourceMirrorInline)
    readonly_fields = ("published_at", "created_at", "updated_at")

    @method_decorator(sensitive_post_parameters())
    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        return super().changeform_view(request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        if obj.status == Resource.Status.PUBLISHED and obj.published_at is None:
            obj.published_at = timezone.now()
        super().save_model(request, obj, form, change)


@admin.action(description="将选中的入口标记为已失效")
def mark_mirrors_failed(modeladmin, request, queryset):
    count = queryset.filter(status=ResourceMirror.Status.ACTIVE).update(
        status=ResourceMirror.Status.FAILED,
        failure_note="管理员批量标记为失效。",
        updated_at=timezone.now(),
    )
    modeladmin.message_user(request, f"已标记 {count} 个失效入口。", messages.SUCCESS)


@admin.register(ResourceMirror)
class ResourceMirrorAdmin(admin.ModelAdmin):
    list_display = ("resource", "provider", "status", "last_verified_at")
    list_filter = ("provider", "status", "last_verified_at")
    search_fields = ("resource__title", "resource__slug", "label")
    readonly_fields = ("last_verified_at", "last_verified_by", "created_at", "updated_at")
    actions = (mark_mirrors_failed,)

    @method_decorator(sensitive_post_parameters())
    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        return super().changeform_view(request, object_id, form_url, extra_context)


@admin.register(ResourceIssue)
class ResourceIssueAdmin(admin.ModelAdmin):
    list_display = ("resource", "issue_type", "reporter", "status", "created_at")
    list_filter = ("issue_type", "status", "created_at")
    search_fields = ("resource__title", "reporter__email", "details")
    readonly_fields = (
        "resource",
        "mirror",
        "reporter",
        "issue_type",
        "details",
        "created_at",
        "resolved_at",
        "resolved_by",
    )

    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        if obj.status == ResourceIssue.Status.OPEN:
            obj.resolved_at = None
            obj.resolved_by = None
        elif obj.resolved_at is None:
            obj.resolved_at = timezone.now()
            obj.resolved_by = request.user
        super().save_model(request, obj, form, change)


class ResourceImportUploadForm(forms.Form):
    file = forms.FileField(
        label="CSV 或 XLSX 文件",
        help_text="最多 5 MiB、500 行。文件只用于生成预览，不会作为资源文件保存。",
    )


class ImportRowInline(admin.TabularInline):
    model = ImportRow
    extra = 0
    can_delete = False
    fields = ("row_number", "state", "errors", "normalized_data", "created_resource")
    readonly_fields = fields
    show_change_link = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.action(description="确认发布校验通过的导入批次")
def confirm_selected_imports(modeladmin, request, queryset):
    confirmed = 0
    for batch in queryset:
        try:
            confirm_import(batch=batch, actor=request.user)
        except (ValidationError, PermissionDenied) as exc:
            modeladmin.message_user(request, f"{batch.filename}：{exc}", messages.ERROR)
        else:
            confirmed += 1
    if confirmed:
        modeladmin.message_user(request, f"已确认发布 {confirmed} 个批次。", messages.SUCCESS)


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    change_list_template = "admin/resources/importbatch/change_list.html"
    list_display = ("filename", "state", "row_count", "error_count", "created_by", "created_at")
    list_filter = ("state", "file_type", "created_at")
    search_fields = ("filename", "file_hash")
    readonly_fields = (
        "filename",
        "file_type",
        "file_hash",
        "state",
        "row_count",
        "error_count",
        "error_message",
        "created_by",
        "created_at",
        "confirmed_by",
        "confirmed_at",
    )
    inlines = (ImportRowInline,)
    actions = (confirm_selected_imports,)

    def get_urls(self):
        custom_urls = [
            path(
                "upload/",
                self.admin_site.admin_view(self.upload_view),
                name="resources_importbatch_upload",
            )
        ]
        return custom_urls + super().get_urls()

    def upload_view(self, request):
        form = ResourceImportUploadForm(request.POST or None, request.FILES or None)
        if request.method == "POST" and form.is_valid():
            batch = preview_import(uploaded_file=form.cleaned_data["file"], actor=request.user)
            if batch.state == ImportBatch.State.READY:
                messages.success(request, "全部行校验通过，请核对预览后再执行“确认发布”。")
            else:
                messages.warning(request, "预览中发现错误，当前批次不能发布。")
            return redirect(reverse("admin:resources_importbatch_change", args=(batch.pk,)))
        context = {
            **self.admin_site.each_context(request),
            "title": "预览导入资源",
            "form": form,
            "opts": self.model._meta,
        }
        return render(request, "admin/resources/importbatch/upload.html", context)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ResourceVersion)
class ResourceVersionAdmin(admin.ModelAdmin):
    list_display = ("resource", "version", "released_on", "is_current")
    list_filter = ("is_current", "released_on")
    search_fields = ("resource__title", "version", "filename")
