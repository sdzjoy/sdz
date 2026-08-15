from allauth.account.decorators import secure_admin_login
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.contrib.sitemaps.views import sitemap
from wagtail.documents import urls as wagtaildocs_urls

from content.feeds import ArticleFeed, NoteFeed
from core.views import healthz, readyz

admin.site.login = secure_admin_login(admin.site.login)

urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("readyz/", readyz, name="readyz"),
    path("sitemap.xml", sitemap, name="sitemap"),
    path("feeds/articles.xml", ArticleFeed(), name="article_feed"),
    path("feeds/notes.xml", NoteFeed(), name="note_feed"),
    path("standards/", include("standards.urls")),
    path("resources/", include("resources.urls")),
    path("account/", include("accounts.urls")),
    path("account/", include("allauth.urls")),
    path("django-admin/", admin.site.urls),
    path("cms/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
    path("", include("allauth.idp.urls")),
    path("", include(wagtail_urls)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
