from django.db import models


class ScheduledTaskState(models.Model):
    name = models.CharField("任务名称", max_length=80, unique=True)
    last_started_at = models.DateTimeField("最近开始", null=True, blank=True)
    last_succeeded_at = models.DateTimeField("最近成功", null=True, blank=True)
    last_error = models.CharField("最近错误", max_length=500, blank=True)
    consecutive_failures = models.PositiveSmallIntegerField("连续失败", default=0)

    class Meta:
        verbose_name = "后台任务状态"
        verbose_name_plural = "后台任务状态"

    def __str__(self):
        return self.name


class MonitorCheck(models.Model):
    class Severity(models.TextChoices):
        CRITICAL = "critical", "严重"
        HIGH = "high", "高"
        MEDIUM = "medium", "中"

    name = models.CharField("检查项", max_length=120)
    url = models.CharField("检查地址", max_length=500)
    severity = models.CharField("等级", max_length=12, choices=Severity.choices)
    ok = models.BooleanField("正常")
    status_code = models.PositiveSmallIntegerField("状态码", null=True, blank=True)
    latency_ms = models.PositiveIntegerField("耗时毫秒", null=True, blank=True)
    error_kind = models.CharField("错误分类", max_length=80, blank=True)
    checked_at = models.DateTimeField("检查时间", auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-checked_at", "-pk")
        verbose_name = "关键路径检查"
        verbose_name_plural = "关键路径检查"

    def __str__(self):
        return f"{self.name} · {'正常' if self.ok else '异常'}"


class AlertIncident(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "待处理"
        RECOVERED = "recovered", "已恢复"

    key = models.CharField("告警标识", max_length=200, unique=True)
    title = models.CharField("告警标题", max_length=300)
    severity = models.CharField("等级", max_length=12, choices=MonitorCheck.Severity.choices)
    status = models.CharField(
        "状态", max_length=12, choices=Status.choices, default=Status.OPEN, db_index=True
    )
    first_seen_at = models.DateTimeField("首次出现", auto_now_add=True)
    last_seen_at = models.DateTimeField("最近出现", auto_now=True)
    recovered_at = models.DateTimeField("恢复时间", null=True, blank=True)

    class Meta:
        ordering = ("-last_seen_at",)
        verbose_name = "运行告警"
        verbose_name_plural = "运行告警"

    def __str__(self):
        return self.title
