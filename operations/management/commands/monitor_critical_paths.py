from django.core.management.base import BaseCommand

from operations.monitoring import run_checks


class Command(BaseCommand):
    help = "检查主站、登录、搜索、规范和暖通工具关键路径并记录分类告警。"

    def handle(self, *args, **options):
        results = run_checks()
        failures = [result for result in results if not result.ok]
        for result in results:
            marker = "OK" if result.ok else result.error_kind or result.status_code
            self.stdout.write(f"{marker} {result.url} {result.latency_ms}ms")
        if failures:
            self.stderr.write(self.style.ERROR(f"{len(failures)} 个关键路径异常。"))

