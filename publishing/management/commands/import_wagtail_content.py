from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from publishing.legacy import LegacyConverter, LegacyVerifier


class Command(BaseCommand):
    help = "把旧内容完整转换到少惰主 CMS；默认只预演并回滚。"

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute",
            action="store_true",
            help="提交转换结果；不提供时在事务中预演后回滚。",
        )
        parser.add_argument(
            "--verify-only",
            action="store_true",
            help="不写入，只核对已经转换的数据。",
        )
        parser.add_argument(
            "--actor-email",
            help="旧记录缺少作者或图片上传人时使用的现有账号。",
        )
        parser.add_argument(
            "--report",
            default="var/legacy-content-report.json",
            help="完整 JSON 报告路径。",
        )
        parser.add_argument(
            "--allow-unmapped",
            action="store_true",
            help="仅供排查：允许报告中存在无法映射的旧块。",
        )

    def _actor(self, email):
        if not email:
            return None
        user = get_user_model().objects.filter(email__iexact=email).first()
        if user is None:
            raise CommandError(f"找不到迁移操作者账号：{email}")
        return user

    def _finish(self, report, *, path, allow_unmapped):
        report.write(path)
        self.stdout.write(f"完整报告：{Path(path).resolve()}")
        self.stdout.write(
            f"新增 {sum(report.created.values())}，更新 {sum(report.updated.values())}，"
            f"差异 {len(report.differences)}，关键问题 {report.critical_count}。"
        )
        if report.differences:
            raise CommandError("旧数据核对失败；已阻止继续切换。")
        if report.critical_count and not allow_unmapped:
            raise CommandError("存在无法可靠转换的旧内容块；已阻止继续切换。")

    def handle(self, *args, **options):
        if options["execute"] and options["verify_only"]:
            raise CommandError("--execute 与 --verify-only 不能同时使用")
        if options["verify_only"]:
            report = LegacyVerifier().run()
            self._finish(
                report,
                path=options["report"],
                allow_unmapped=options["allow_unmapped"],
            )
            self.stdout.write(self.style.SUCCESS("旧数据核对通过。"))
            return

        actor = self._actor(options["actor_email"])
        with transaction.atomic():
            import_report = LegacyConverter(actor=actor).run()
            verify_report = LegacyVerifier().run()
            import_report.issues.extend(verify_report.issues)
            import_report.differences.extend(verify_report.differences)
            if not options["execute"]:
                transaction.set_rollback(True)
            self._finish(
                import_report,
                path=options["report"],
                allow_unmapped=options["allow_unmapped"],
            )

        if options["execute"]:
            self.stdout.write(self.style.SUCCESS("旧内容已转换并通过核对。"))
        else:
            self.stdout.write(self.style.SUCCESS("预演通过；所有数据库写入已回滚。"))
