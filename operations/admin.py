from django.contrib import admin

from .models import AlertIncident, MonitorCheck, ScheduledTaskState


@admin.register(ScheduledTaskState)
class ScheduledTaskStateAdmin(admin.ModelAdmin):
    list_display = ("name", "last_succeeded_at", "consecutive_failures")
    readonly_fields = [field.name for field in ScheduledTaskState._meta.fields]


@admin.register(MonitorCheck)
class MonitorCheckAdmin(admin.ModelAdmin):
    list_display = ("name", "severity", "ok", "status_code", "latency_ms", "checked_at")
    list_filter = ("ok", "severity", "checked_at")
    readonly_fields = [field.name for field in MonitorCheck._meta.fields]


@admin.register(AlertIncident)
class AlertIncidentAdmin(admin.ModelAdmin):
    list_display = ("title", "severity", "status", "last_seen_at")
    list_filter = ("status", "severity")
    readonly_fields = [field.name for field in AlertIncident._meta.fields]

