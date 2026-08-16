from django.contrib.sitemaps import Sitemap
from django.db import models

from publishing.models import ContentEntry, ContentRevision


class StaticPublishingSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return (
            "/",
            "/articles/",
            "/projects/",
            "/notes/",
            "/tools/",
            "/about/",
        )

    def location(self, item):
        return item


class PublishedContentSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.6

    def items(self):
        return ContentEntry.objects.published().annotate(
            public_lastmod=models.Max(
                "revisions__created_at",
                filter=models.Q(revisions__action=ContentRevision.Action.PUBLISH),
            )
        )

    def location(self, item):
        return item.get_absolute_url()

    def lastmod(self, item):
        return item.public_lastmod or item.published_at


SITEMAPS = {
    "publishing-static": StaticPublishingSitemap,
    "publishing-content": PublishedContentSitemap,
}
