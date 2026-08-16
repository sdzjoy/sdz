import json
from functools import lru_cache

from django import template
from django.conf import settings
from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeString

register = template.Library()


def _manifest_paths():
    return (
        settings.BASE_DIR / "static" / "studio" / "dist" / ".vite" / "manifest.json",
        settings.STATIC_ROOT / "studio" / "dist" / ".vite" / "manifest.json",
    )


@lru_cache(maxsize=1)
def _manifest():
    for path in _manifest_paths():
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _asset_url(path):
    return f"{settings.STATIC_URL}studio/dist/{path}"


@register.simple_tag
def studio_vite_assets(entry="src/article-editor.ts"):
    manifest = _manifest()
    item = manifest.get(entry)
    if not item:
        return SafeString("")
    styles = format_html_join(
        "",
        '<link rel="stylesheet" href="{}">',
        ((_asset_url(path),) for path in item.get("css", [])),
    )
    script = format_html(
        '<script type="module" src="{}"></script>',
        _asset_url(item["file"]),
    )
    return format_html("{}{}", styles, script)
