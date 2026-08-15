from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import UserManager


class User(AbstractUser):
    class MembershipLevel(models.TextChoices):
        MEMBER = "L1", "普通会员"
        TRUSTED = "L2", "高级会员"
        OWNER = "L3", "站长"

    username = None
    email = models.EmailField("邮箱", unique=True)
    display_name = models.CharField("显示名称", max_length=80, blank=True)
    membership_level = models.CharField(
        "会员等级",
        max_length=2,
        choices=MembershipLevel.choices,
        default=MembershipLevel.MEMBER,
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
