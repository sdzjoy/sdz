from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    class Action(models.TextChoices):
        BULK_PUBLISH = "bulk_publish", "批量发布"
        BULK_UNPUBLISH = "bulk_unpublish", "批量取消发布"
        MOVE_TO_TRASH = "move_to_trash", "移入回收站"
        RESTORE_FROM_TRASH = "restore_from_trash", "移出回收站"
        PERMANENT_DELETE = "permanent_delete", "永久删除"
        MANUAL_SAVE = "manual_save", "手工保存"
        PUBLISH = "publish", "发布内容"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="studio_audit_events",
        verbose_name="操作人",
    )
    action = models.CharField("动作", max_length=32, choices=Action.choices, db_index=True)
    object_type = models.CharField("对象类型", max_length=40)
    object_id = models.CharField("对象标识", max_length=64)
    object_label = models.CharField("对象名称", max_length=240)
    reason = models.CharField("操作原因", max_length=500, blank=True)
    metadata = models.JSONField("非敏感附加信息", default=dict, blank=True)
    created_at = models.DateTimeField("操作时间", auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "后台审计记录"
        verbose_name_plural = "后台审计记录"
        indexes = [
            models.Index(
                fields=("object_type", "object_id", "-created_at"),
                name="studio_audit_object_idx",
            )
        ]

    def __str__(self):
        return f"{self.get_action_display()} · {self.object_label}"
