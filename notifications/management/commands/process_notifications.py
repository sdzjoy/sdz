from django.core.management.base import BaseCommand

from notifications.models import Event
from notifications.services import materialize_event, process_email_deliveries


class Command(BaseCommand):
    help = "生成站内通知并处理有限重试的邮件投递队列。"

    def add_arguments(self, parser):
        parser.add_argument("--max-attempts", type=int, default=3)

    def handle(self, *args, **options):
        materialized = 0
        events = Event.objects.filter(materialized_at__isnull=True).order_by("created_at")[:200]
        for event in events:
            materialized += materialize_event(event)
        results = process_email_deliveries(max_attempts=max(1, options["max_attempts"]))
        self.stdout.write(
            self.style.SUCCESS(
                f"站内通知 {materialized} 条；邮件发送 {results['sent']}，"
                f"取消 {results['skipped']}，最终失败 {results['failed']}。"
            )
        )
