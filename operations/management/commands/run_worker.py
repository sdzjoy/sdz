import time
from datetime import timedelta

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from operations.models import ScheduledTaskState

TASKS = (
    ("notifications", "process_notifications", timedelta(seconds=20)),
    ("critical_paths", "monitor_critical_paths", timedelta(minutes=5)),
    ("weekly_digest", "queue_weekly_digests", timedelta(days=7)),
    # Standards data is deliberately low-frequency and still requires human review.
    ("standard_sources", "check_standard_sources", timedelta(days=30)),
)


class Command(BaseCommand):
    help = "运行轻量后台任务，不在网页请求中发送邮件或抓取外部数据。"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def _run_due_tasks(self):
        now = timezone.now()
        for name, command, interval in TASKS:
            state, _ = ScheduledTaskState.objects.get_or_create(name=name)
            if state.last_started_at and state.last_started_at + interval > now:
                continue
            state.last_started_at = now
            state.save(update_fields=("last_started_at",))
            try:
                call_command(command, verbosity=0)
            except Exception as exc:
                state.consecutive_failures += 1
                state.last_error = f"{type(exc).__name__}: {exc}"[:500]
                state.save(update_fields=("consecutive_failures", "last_error"))
                continue
            state.last_succeeded_at = timezone.now()
            state.consecutive_failures = 0
            state.last_error = ""
            state.save(
                update_fields=("last_succeeded_at", "consecutive_failures", "last_error")
            )

    def handle(self, *args, **options):
        while True:
            self._run_due_tasks()
            if options["once"]:
                break
            time.sleep(max(5, settings.NOTIFICATION_WORKER_INTERVAL))
