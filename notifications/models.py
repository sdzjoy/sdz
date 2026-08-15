from django.conf import settings
from django.db import models


class Event(models.Model):
    class EventType(models.TextChoices):
        STANDARD_CHANGED = "standard_changed", "标准信息变更"
        STANDARD_STATUS_CHANGED = "standard_status_changed", "标准状态变更"
        STANDARD_ADDED = "standard_added", "新增标准"
        RESOURCE_IMPORTANT = "resource_important", "重要资源变化"
        CONTENT_PUBLISHED = "content_published", "内容发布"
        MEMBERSHIP_CHANGED = "membership_changed", "会员等级变化"
        SECURITY = "security", "账号安全"

    class Priority(models.TextChoices):
        IMMEDIATE = "immediate", "即时"
        DIGEST = "digest", "周报"

    event_type = models.CharField("事件类型", max_length=32, choices=EventType.choices)
    title = models.CharField("事件标题", max_length=300)
    payload = models.JSONField("事件数据", default=dict)
    priority = models.CharField(
        "通知节奏", max_length=12, choices=Priority.choices, default=Priority.IMMEDIATE
    )
    dedupe_key = models.CharField("去重标识", max_length=200, unique=True)
    created_at = models.DateTimeField("产生时间", auto_now_add=True, db_index=True)
    materialized_at = models.DateTimeField("生成用户通知时间", null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "站内事件"
        verbose_name_plural = "站内事件"

    def __str__(self):
        return self.title


class ContentReference(models.TextChoices):
    PROJECT = "project", "项目"
    ARTICLE = "article", "文章"
    NOTE = "note", "随记"
    STANDARD = "standard", "规范"
    RESOURCE = "resource", "资源"
    TOOL = "tool", "工具"


class Favorite(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorites"
    )
    item_type = models.CharField("内容类型", max_length=16, choices=ContentReference.choices)
    object_id = models.CharField("对象标识", max_length=64)
    created_at = models.DateTimeField("收藏时间", auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "收藏"
        verbose_name_plural = "收藏"
        constraints = [
            models.UniqueConstraint(
                fields=("user", "item_type", "object_id"), name="unique_favorite_item"
            )
        ]

    def __str__(self):
        return f"{self.user} · {self.get_item_type_display()} · {self.object_id}"


class ItemSubscription(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="item_subscriptions"
    )
    item_type = models.CharField("内容类型", max_length=16, choices=ContentReference.choices)
    object_id = models.CharField("对象标识", max_length=64)
    created_at = models.DateTimeField("订阅时间", auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "单项订阅"
        verbose_name_plural = "单项订阅"
        constraints = [
            models.UniqueConstraint(
                fields=("user", "item_type", "object_id"),
                name="unique_item_subscription",
            )
        ]

    def __str__(self):
        return f"{self.user} · {self.get_item_type_display()} · {self.object_id}"


class TopicSubscription(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="topic_subscriptions"
    )
    taxonomy = models.ForeignKey(
        "standards.TaxonomyTerm",
        on_delete=models.CASCADE,
        related_name="notification_subscriptions",
        verbose_name="主题",
    )
    created_at = models.DateTimeField("订阅时间", auto_now_add=True)

    class Meta:
        ordering = ("taxonomy__sort_order", "taxonomy__name")
        verbose_name = "主题订阅"
        verbose_name_plural = "主题订阅"
        constraints = [
            models.UniqueConstraint(
                fields=("user", "taxonomy"), name="unique_topic_subscription"
            )
        ]

    def __str__(self):
        return f"{self.user} · {self.taxonomy}"


class NotificationPreference(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preference",
    )
    email_enabled = models.BooleanField("接收邮件", default=True)
    immediate_standard = models.BooleanField("重要规范变化", default=True)
    immediate_resource = models.BooleanField("重要资源变化", default=True)
    membership = models.BooleanField("会员等级变化", default=True)
    weekly_digest = models.BooleanField("每周内容摘要", default=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "通知偏好"
        verbose_name_plural = "通知偏好"

    def __str__(self):
        return str(self.user)


class UserNotification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField("标题", max_length=300)
    body = models.TextField("摘要", blank=True, max_length=2000)
    url = models.CharField("站内地址", max_length=500, blank=True)
    created_at = models.DateTimeField("通知时间", auto_now_add=True, db_index=True)
    read_at = models.DateTimeField("阅读时间", null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "站内通知"
        verbose_name_plural = "站内通知"
        constraints = [
            models.UniqueConstraint(
                fields=("user", "event"), name="unique_user_event_notification"
            )
        ]

    def __str__(self):
        return f"{self.user} · {self.title}"


class EmailDelivery(models.Model):
    class DeliveryType(models.TextChoices):
        IMMEDIATE = "immediate", "即时通知"
        WEEKLY = "weekly", "每周摘要"

    class Status(models.TextChoices):
        PENDING = "pending", "待发送"
        SENDING = "sending", "发送中"
        RETRY = "retry", "等待重试"
        SENT = "sent", "已发送"
        SKIPPED = "skipped", "已取消"
        FAILED = "failed", "发送失败"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="email_deliveries"
    )
    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="email_deliveries", null=True, blank=True
    )
    delivery_type = models.CharField("邮件类型", max_length=12, choices=DeliveryType.choices)
    category = models.CharField("偏好类别", max_length=32)
    subject = models.CharField("主题", max_length=300)
    body = models.TextField("正文")
    idempotency_key = models.CharField("幂等标识", max_length=240, unique=True)
    status = models.CharField(
        "状态", max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    attempts = models.PositiveSmallIntegerField("尝试次数", default=0)
    next_attempt_at = models.DateTimeField("下次尝试", null=True, blank=True)
    claimed_at = models.DateTimeField("领取时间", null=True, blank=True)
    last_error = models.CharField("最近错误", max_length=500, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    sent_at = models.DateTimeField("发送时间", null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "邮件投递"
        verbose_name_plural = "邮件投递"

    def __str__(self):
        return f"{self.user} · {self.subject}"
