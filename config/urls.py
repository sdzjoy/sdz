from allauth.account.decorators import secure_admin_login
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path

from operations.views import healthz, readyz
from publishing.feeds import ArticleFeed, NoteFeed
from publishing.sitemaps import SITEMAPS

admin.site.login = secure_admin_login(admin.site.login)

urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("readyz/", readyz, name="readyz"),
    path("sitemap.xml", sitemap, {"sitemaps": SITEMAPS}, name="sitemap"),
    path("feeds/articles.xml", ArticleFeed(), name="article_feed"),
    path("feeds/notes.xml", NoteFeed(), name="note_feed"),
    path("search/", include("searchapp.urls")),
    path("standards/", include("standards.urls")),
    path("resources/", include("resources.urls")),
    path("account/", include("notifications.urls")),
    path("account/", include("accounts.urls")),
    path("account/", include("allauth.urls")),
    path("django-admin/", admin.site.urls),
    path("cms/", include("studio.urls")),
    path("", include("allauth.idp.urls")),
    path("", include("publishing.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
