from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.syndication.views import Feed

from publishing.models import ContentEntry


def publication_datetime(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value).date()
    return datetime.combine(value, time.min, tzinfo=ZoneInfo(settings.TIME_ZONE))


def _published_type_value(item, field):
    metadata = item.published_metadata if isinstance(item.published_metadata, dict) else {}
    type_metadata = metadata.get("type", {})
    return type_metadata.get(field) if isinstance(type_metadata, dict) else None


class PublishedContentFeed(Feed):
    author_name = "少惰主"

    def item_title(self, item):
        return item.published_title

    def item_description(self, item):
        return item.published_summary

    def item_link(self, item):
        return item.get_absolute_url()

    def item_categories(self, item):
        return list(item.published_topics.values_list("name", flat=True))

    def item_updateddate(self, item):
        return item.published_at


class ArticleFeed(PublishedContentFeed):
    title = "少惰主 · 文章"
    link = "/articles/"
    description = "经过整理和验证的工程、系统与数字生活技术文章。"

    def items(self):
        return (
            ContentEntry.objects.published()
            .filter(kind=ContentEntry.Kind.ARTICLE)
            .prefetch_related("published_topics")
            .order_by("-published_at")[:20]
        )

    def item_pubdate(self, item):
        value = _published_type_value(item, "published_on")
        return publication_datetime(value) if value else item.published_at


class NoteFeed(PublishedContentFeed):
    title = "少惰主 · 随记"
    link = "/notes/"
    description = "现场片段、实验记录与阶段性技术判断。"

    def items(self):
        return (
            ContentEntry.objects.published()
            .filter(kind=ContentEntry.Kind.NOTE)
            .prefetch_related("published_topics")
            .order_by("-published_at")[:30]
        )

    def item_pubdate(self, item):
        value = _published_type_value(item, "noted_on")
        return publication_datetime(value) if value else item.published_at
