from studio.templatetags.studio_assets import _manifest_styles


def test_vite_asset_styles_follow_imported_chunks_and_deduplicate_paths():
    manifest = {
        "src/article-editor.ts": {
            "file": "assets/article.js",
            "imports": ["src/editor.ts", "src/editor.ts"],
        },
        "src/editor.ts": {
            "file": "assets/editor.js",
            "css": ["assets/editor.css"],
        },
    }

    assert _manifest_styles(manifest, "src/article-editor.ts") == [
        "assets/editor.css"
    ]
