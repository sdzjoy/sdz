from django.core.management.base import BaseCommand

from notifications.services import queue_weekly_digests


class Command(BaseCommand):
    help = "按用户当前偏好生成幂等的每周摘要邮件。"

    def handle(self, *args, **options):
        count = queue_weekly_digests()
        self.stdout.write(self.style.SUCCESS(f"已生成 {count} 封每周摘要。"))

