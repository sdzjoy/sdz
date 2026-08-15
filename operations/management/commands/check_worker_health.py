from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from operations.models import ScheduledTaskState


class Command(BaseCommand):
    help = "确认后台任务循环最近仍在运行。"

    def handle(self, *args, **options):
        state = ScheduledTaskState.objects.filter(name="notifications").first()
        if not state or not state.last_started_at:
            raise CommandError("后台任务尚未报告运行状态。")
        if state.last_started_at < timezone.now() - timedelta(minutes=10):
            raise CommandError("后台任务状态已超过 10 分钟未更新。")
        self.stdout.write("worker ready")

