from django.db import models


class Event(models.Model):
    class EventType(models.TextChoices):
        STANDARD_CHANGED = "standard_changed", "标准信息变更"
        STANDARD_STATUS_CHANGED = "standard_status_changed", "标准状态变更"
        STANDARD_ADDED = "standard_added", "新增标准"

    event_type = models.CharField("事件类型", max_length=32, choices=EventType.choices)
    title = models.CharField("事件标题", max_length=300)
    payload = models.JSONField("事件数据", default=dict)
    dedupe_key = models.CharField("去重标识", max_length=200, unique=True)
    created_at = models.DateTimeField("产生时间", auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "站内事件"
        verbose_name_plural = "站内事件"

    def __str__(self):
        return self.title
