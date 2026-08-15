from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models

from .managers import UserManager


class User(AbstractUser):
    class MembershipLevel(models.TextChoices):
        PENDING = "L0", "待验证"
        MEMBER = "L1", "普通会员"
        TRUSTED = "L2", "高级会员"
        OWNER = "L3", "站长"

    username = None
    email = models.EmailField("邮箱", unique=True)
    display_name = models.CharField("显示名称", max_length=80, blank=True)
    email_verified_at = models.DateTimeField("邮箱验证时间", null=True, blank=True)
    membership_level = models.CharField(
        "会员等级",
        max_length=2,
        choices=MembershipLevel.choices,
        default=MembershipLevel.PENDING,
        db_index=True,
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = "用户"
        verbose_name_plural = "用户"

    def __str__(self):
        return self.display_name or self.email

    def has_membership_level(self, required_level):
        rank = {
            self.MembershipLevel.PENDING: 0,
            self.MembershipLevel.MEMBER: 1,
            self.MembershipLevel.TRUSTED: 2,
            self.MembershipLevel.OWNER: 3,
        }
        return self.is_active and rank[self.membership_level] >= rank[required_level]


class MembershipChange(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="membership_changes",
        verbose_name="用户",
    )
    from_level = models.CharField(
        "原等级", max_length=2, choices=User.MembershipLevel.choices
    )
    to_level = models.CharField(
        "新等级", max_length=2, choices=User.MembershipLevel.choices
    )
    reason = models.CharField("变更原因", max_length=240)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="membership_changes_made",
        null=True,
        blank=True,
        verbose_name="操作人",
    )
    created_at = models.DateTimeField("操作时间", auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        verbose_name = "会员等级变更"
        verbose_name_plural = "会员等级变更"
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(from_level=models.F("to_level")),
                name="membership_change_requires_different_levels",
            )
        ]

    def __str__(self):
        return f"{self.user}: {self.from_level} → {self.to_level}"


class AccountRequest(models.Model):
    class RequestType(models.TextChoices):
        DEACTIVATE = "deactivate", "停用账号"
        EXPORT = "export", "导出数据"
        DELETE = "delete", "删除账号"

    class Status(models.TextChoices):
        PENDING = "pending", "待处理"
        COMPLETED = "completed", "已完成"
        REJECTED = "rejected", "已拒绝"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="account_requests",
        verbose_name="用户",
    )
    request_type = models.CharField(
        "申请类型", max_length=16, choices=RequestType.choices
    )
    status = models.CharField(
        "状态", max_length=12, choices=Status.choices, default=Status.PENDING
    )
    note = models.TextField("用户说明", blank=True, max_length=1000)
    resolution_note = models.TextField("处理说明", blank=True, max_length=1000)
    requested_at = models.DateTimeField("申请时间", auto_now_add=True, db_index=True)
    processed_at = models.DateTimeField("处理时间", null=True, blank=True)
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="account_requests_processed",
        null=True,
        blank=True,
        verbose_name="处理人",
    )

    class Meta:
        ordering = ("-requested_at", "-pk")
        verbose_name = "账号请求"
        verbose_name_plural = "账号请求"
        constraints = [
            models.UniqueConstraint(
                fields=("user", "request_type"),
                condition=models.Q(status="pending"),
                name="one_pending_account_request_per_type",
            )
        ]

    def __str__(self):
        return f"{self.user} · {self.get_request_type_display()}"

    def clean(self):
        if self.status == self.Status.PENDING and self.processed_at:
            raise ValidationError({"processed_at": "待处理申请不能填写处理时间。"})
        if self.status != self.Status.PENDING and not self.processed_at:
            raise ValidationError({"processed_at": "已处理申请必须填写处理时间。"})
