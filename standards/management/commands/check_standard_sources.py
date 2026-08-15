from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from standards.models import CheckBatch, MonitoringSource
from standards.monitoring import run_source_check


class Command(BaseCommand):
    help = "顺序检查已明确允许访问且到期的规范增量来源。"

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            action="append",
            default=[],
            help="只检查指定来源标识；可重复使用。",
        )

    def handle(self, *args, **options):
        sources = MonitoringSource.objects.filter(
            enabled=True,
            automated_access_allowed=True,
            feed_format=MonitoringSource.FeedFormat.SDZJOY_JSON,
        )
        selected = options["source"]
        if selected:
            sources = sources.filter(slug__in=selected)
            missing = set(selected) - set(sources.values_list("slug", flat=True))
            if missing:
                raise CommandError("来源未启用或未获允许：" + "、".join(sorted(missing)))
        else:
            now = timezone.now()
            sources = sources.filter(
                Q(next_check_at__isnull=True) | Q(next_check_at__lte=now),
                Q(next_allowed_at__isnull=True) | Q(next_allowed_at__lte=now),
            )

        checked = 0
        for source in sources.order_by("name"):
            batch = run_source_check(
                source=source,
                trigger=CheckBatch.Trigger.SCHEDULED,
            )
            checked += 1
            self.stdout.write(f"{source.slug}: {batch.get_status_display()} · {batch.message}")
        self.stdout.write(self.style.SUCCESS(f"本次顺序处理 {checked} 个来源。"))
