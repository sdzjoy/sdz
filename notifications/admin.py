from django.contrib import admin

from .models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "event_type", "created_at")
    list_filter = ("event_type", "created_at")
    search_fields = ("title", "dedupe_key")
    readonly_fields = ("event_type", "title", "payload", "dedupe_key", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
