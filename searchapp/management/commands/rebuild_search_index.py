from django.core.management.base import BaseCommand

from searchapp.services import rebuild_index


class Command(BaseCommand):
    help = "重建统一搜索记录，并移除已经下线或无权公开的旧记录。"

    def handle(self, *args, **options):
        count = rebuild_index()
        self.stdout.write(self.style.SUCCESS(f"已重建 {count} 条搜索记录。"))

