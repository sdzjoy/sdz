from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.syndication.views import Feed

from .models import ArticlePage, NotePage


def publication_datetime(value):
    return datetime.combine(value, time.min, tzinfo=ZoneInfo(settings.TIME_ZONE))


class PublishedContentFeed(Feed):
    author_name = "少惰主"

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return item.summary

    def item_link(self, item):
        return item.full_url or item.url

    def item_categories(self, item):
        return list(item.topics.values_list("name", flat=True))


class ArticleFeed(PublishedContentFeed):
    title = "少惰主 · 文章"
    link = "/articles/"
    description = "经过整理和验证的工程、系统与数字生活技术文章。"

    def items(self):
        return ArticlePage.objects.live().public().order_by("-published_on")[:20]

    def item_pubdate(self, item):
        return publication_datetime(item.published_on)


class NoteFeed(PublishedContentFeed):
    title = "少惰主 · 随记"
    link = "/notes/"
    description = "现场片段、实验记录与阶段性技术判断。"

    def items(self):
        return NotePage.objects.live().public().order_by("-noted_on")[:30]

    def item_pubdate(self, item):
        return publication_datetime(item.noted_on)
