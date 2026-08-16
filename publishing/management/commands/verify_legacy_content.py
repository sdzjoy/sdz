from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from publishing.legacy import LegacyVerifier


class Command(BaseCommand):
    help = "逐项核对旧内容与已经转换的新内容；发现关键差异时失败。"

    def add_arguments(self, parser):
        parser.add_argument(
            "--report",
            default="var/legacy-verification-report.json",
            help="完整 JSON 报告路径。",
        )
        parser.add_argument(
            "--allow-unmapped",
            action="store_true",
            help="仅供排查：允许报告中存在无法映射的旧块。",
        )

    def handle(self, *args, **options):
        report = LegacyVerifier().run()
        report.write(options["report"])
        self.stdout.write(f"完整报告：{Path(options['report']).resolve()}")
        self.stdout.write(
            f"差异 {len(report.differences)}，关键问题 {report.critical_count}。"
        )
        if report.differences:
            raise CommandError("旧数据核对失败；已阻止继续切换。")
        if report.critical_count and not options["allow_unmapped"]:
            raise CommandError("存在无法可靠转换的旧内容块；已阻止继续切换。")
        self.stdout.write(self.style.SUCCESS("旧数据核对通过。"))
