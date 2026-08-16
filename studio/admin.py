from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("action", "object_label", "actor", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("object_label", "object_id", "reason", "actor__email")
    readonly_fields = (
        "actor",
        "action",
        "object_type",
        "object_id",
        "object_label",
        "reason",
        "metadata",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
