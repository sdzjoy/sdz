from django.contrib import admin

from .models import (
    EmailDelivery,
    Event,
    Favorite,
    ItemSubscription,
    NotificationPreference,
    TopicSubscription,
    UserNotification,
)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "event_type", "created_at")
    list_filter = ("event_type", "created_at")
    search_fields = ("title", "dedupe_key")
    readonly_fields = (
        "event_type",
        "title",
        "payload",
        "priority",
        "dedupe_key",
        "created_at",
        "materialized_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EmailDelivery)
class EmailDeliveryAdmin(admin.ModelAdmin):
    list_display = ("subject", "user", "delivery_type", "status", "attempts", "created_at")
    list_filter = ("status", "delivery_type", "category", "created_at")
    search_fields = ("subject", "user__email", "idempotency_key", "last_error")
    readonly_fields = [field.name for field in EmailDelivery._meta.fields]

    def has_add_permission(self, request):
        return False


admin.site.register(Favorite)
admin.site.register(ItemSubscription)
admin.site.register(TopicSubscription)
admin.site.register(NotificationPreference)
admin.site.register(UserNotification)
