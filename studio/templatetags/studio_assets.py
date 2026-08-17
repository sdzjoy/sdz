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


def _manifest_styles(manifest, entry):
    styles = []
    visited_entries = set()
    visited_styles = set()

    def visit(name):
        if name in visited_entries:
            return
        visited_entries.add(name)
        item = manifest.get(name) or {}
        for path in item.get("css", []):
            if path not in visited_styles:
                visited_styles.add(path)
                styles.append(path)
        for imported in item.get("imports", []):
            visit(imported)

    visit(entry)
    return styles


@register.simple_tag
def studio_vite_assets(entry="src/article-editor.ts"):
    manifest = _manifest()
    item = manifest.get(entry)
    if not item:
        return SafeString("")
    styles = format_html_join(
        "",
        '<link rel="stylesheet" href="{}">',
        ((_asset_url(path),) for path in _manifest_styles(manifest, entry)),
    )
    script = format_html(
        '<script type="module" src="{}"></script>',
        _asset_url(item["file"]),
    )
    return format_html("{}{}", styles, script)
