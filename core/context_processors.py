from django.conf import settings

SITE_NAVIGATION = (
    {"key": "projects", "label": "项目", "url": "/projects/"},
    {"key": "articles", "label": "文章", "url": "/articles/"},
    {"key": "notes", "label": "随记", "url": "/notes/"},
    {"key": "tools", "label": "工具", "url": "/tools/"},
    {"key": "about", "label": "关于", "url": "/about/"},
)

LIVE_SUBSITES = (
    {"label": "暖通参数库", "url": "https://hvac.sdzjoy.com/"},
)


def site_shell(request):
    origin = settings.PUBLIC_SITE_ORIGIN.rstrip("/")
    canonical_url = (
        f"{origin}{request.path}" if origin else request.build_absolute_uri(request.path)
    )
    return {
        "canonical_url": canonical_url,
        "current_section": request.path.strip("/").partition("/")[0],
        "site_navigation": SITE_NAVIGATION,
        "live_subsites": LIVE_SUBSITES,
    }
