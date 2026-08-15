from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.documents import urls as wagtaildocs_urls

from core.views import healthz, readyz

urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("readyz/", readyz, name="readyz"),
    path("cms/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
    path("", include(wagtail_urls)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
