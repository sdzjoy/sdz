from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from publishing.models import ContentEntry
from studio.models import AuditEvent
from studio.permissions import StudioRole, get_studio_role

MINIMUM_TRASH_AGE = timedelta(days=30)
DEFAULT_LIMIT = 100


class Command(BaseCommand):
    help = "预览或永久清理进入回收站满 30 天的内容。默认只预览。"

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute",
            action="store_true",
            help="实际永久删除；不提供时只显示可清理数量。",
        )
        parser.add_argument(
            "--actor-email",
            help="执行清理的站长账号邮箱；实际删除时必填。",
        )
        parser.add_argument(
            "--reason",
            default="回收站满 30 天批量清理",
            help="写入审计记录的清理原因，至少 5 个字。",
        )
        parser.add_argument(
            "--content-id",
            action="append",
            type=int,
            dest="content_ids",
            help="只清理指定内容，可重复使用。",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=DEFAULT_LIMIT,
            help=f"单次最多处理数量，默认 {DEFAULT_LIMIT}。",
        )

    def handle(self, *args, **options):
        if options["limit"] < 1 or options["limit"] > 1000:
            raise CommandError("--limit 必须在 1 到 1000 之间。")

        cutoff = timezone.now() - MINIMUM_TRASH_AGE
        queryset = ContentEntry.objects.in_trash().filter(deleted_at__lte=cutoff)
        if options["content_ids"]:
            queryset = queryset.filter(pk__in=options["content_ids"])
        candidates = list(queryset.order_by("deleted_at", "pk")[: options["limit"]])

        if not options["execute"]:
            self.stdout.write(
                f"预览：共有 {len(candidates)} 项内容已进入回收站满 30 天；未删除任何内容。"
            )
            for item in candidates:
                self.stdout.write(f"- {item.pk} · {item.get_kind_display()} · {item.title}")
            return

        actor_email = (options["actor_email"] or "").strip()
        reason = options["reason"].strip()
        if not actor_email:
            raise CommandError("实际清理必须提供 --actor-email。")
        if len(reason) < 5:
            raise CommandError("--reason 至少需要 5 个字。")
        user_model = get_user_model()
        try:
            actor = user_model.objects.get(email__iexact=actor_email)
        except user_model.DoesNotExist as error:
            raise CommandError("找不到指定的操作账号。") from error
        if get_studio_role(actor) != StudioRole.OWNER:
            raise CommandError("只有站长账号可以永久清理回收站。")

        deleted = 0
        skipped = 0
        for item in candidates:
            object_id = item.pk
            object_kind = item.kind
            object_title = item.title
            deleted_at = item.deleted_at.isoformat()
            try:
                with transaction.atomic():
                    item.delete()
                    AuditEvent.objects.create(
                        actor=actor,
                        action=AuditEvent.Action.PERMANENT_DELETE,
                        object_type=object_kind,
                        object_id=str(object_id),
                        object_label=object_title,
                        reason=reason,
                        metadata={
                            "source": "purge_deleted_content",
                            "deleted_at": deleted_at,
                        },
                    )
            except ProtectedError:
                skipped += 1
                self.stderr.write(
                    self.style.WARNING(f"跳过 {object_id} · {object_title}：仍被其他记录引用。")
                )
                continue
            deleted += 1

        self.stdout.write(self.style.SUCCESS(f"已永久清理 {deleted} 项；跳过 {skipped} 项。"))
