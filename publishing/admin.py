from django.contrib import admin

from .models import Article, Asset, ContentRevision, Note, Project, SiteProfile, Tool, Topic


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "accent", "updated_at")
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ("original_name", "kind", "mime_type", "byte_size", "created_at")
    list_filter = ("kind", "mime_type")
    search_fields = ("original_name", "title", "alt_text", "sha256")
    readonly_fields = ("byte_size", "width", "height", "sha256", "created_at", "updated_at")


class ContentAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "featured", "version", "updated_at", "deleted_at")
    list_filter = ("status", "featured")
    search_fields = ("title", "slug", "summary", "body_text")
    readonly_fields = (
        "kind",
        "rendered_html",
        "body_text",
        "published_rendered_html",
        "published_body_text",
        "version",
        "created_at",
        "updated_at",
        "deleted_at",
        "deleted_by",
    )


admin.site.register(Article, ContentAdmin)
admin.site.register(Project, ContentAdmin)
admin.site.register(Note, ContentAdmin)
admin.site.register(Tool, ContentAdmin)
admin.site.register(SiteProfile)


@admin.register(ContentRevision)
class ContentRevisionAdmin(admin.ModelAdmin):
    list_display = ("content", "number", "action", "created_by", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("content__title", "summary")
    readonly_fields = (
        "content",
        "number",
        "action",
        "snapshot",
        "summary",
        "created_by",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
