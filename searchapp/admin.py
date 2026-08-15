from django.contrib import admin

from .models import SearchDocument


@admin.register(SearchDocument)
class SearchDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "access_level", "indexed_at")
    list_filter = ("kind", "access_level")
    search_fields = ("title", "summary")
    readonly_fields = [field.name for field in SearchDocument._meta.fields]

    def has_add_permission(self, request):
        return False

