import json
from datetime import date
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from wagtail.images import get_image_model

from accounts.models import User
from content.models import ArticleIndexPage, ArticlePage
from content.models import Topic as LegacyTopic
from notifications.models import Favorite
from publishing.documents import extract_text, render_document, validate_document
from publishing.legacy import LegacyConverter, LegacyVerifier, streamfield_to_document
from publishing.models import Article, Asset, ContentEntry, Topic

pytestmark = pytest.mark.django_db
FIXTURE = Path(__file__).parent / "fixtures" / "legacy_content.json"
PASSWORD = "a-safe-test-password"  # noqa: S105


def _section(model):
    return model.objects.get(depth=3)


def _published_article(
    *, owner, title="旧文章", slug="legacy-article", body=None, cover_image=None
):
    page = ArticlePage(
        title=title,
        slug=slug,
        summary="旧系统摘要",
        published_on=date(2026, 8, 15),
        body=body or [("markdown", "旧系统正文")],
        cover_image=cover_image,
        owner=owner,
        live=False,
    )
    _section(ArticleIndexPage).add_child(instance=page)
    page.save_revision().publish()
    page.refresh_from_db()
    return page


def test_fixture_stream_blocks_convert_to_valid_versioned_tiptap_document():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    result = streamfield_to_document(fixture["blocks"])
    validated = validate_document(result.document)
    node_types = {node["type"] for node in validated.doc["content"]}
    html = render_document(validated)

    assert result.issues == []
    assert {"heading", "callout", "equation", "table", "parameterCard", "codeBlock"} <= node_types
    assert "冷通道" in extract_text(validated)
    assert 'href="https://example.com/source"' in html
    assert "<script" not in html


def test_unmapped_block_preserves_raw_source_and_is_critical():
    result = streamfield_to_document(
        [{"type": "future_hvac_widget", "value": {"secret_formula": "x+y", "items": [1, 2]}}],
        source_model="ArticlePage",
        source_id=42,
    )

    node = result.document["doc"]["content"][0]
    raw = "".join(node["attrs"]["rawChunks"])

    assert node["type"] == "legacyBlock"
    assert json.loads(raw) == {"secret_formula": "x+y", "items": [1, 2]}
    assert [(issue.severity, issue.code) for issue in result.issues] == [
        ("critical", "unmapped_block")
    ]
    assert "future_hvac_widget" in render_document(result.document)


def test_converter_keeps_snapshots_media_references_and_is_repeatable(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    owner = User.objects.create_user("legacy-owner@example.com", PASSWORD)
    image = get_image_model().objects.create(
        title="冷却系统示意图",
        uploaded_by_user=owner,
        file=SimpleUploadedFile(
            "cooling.png",
            (
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
                b"\x00\x00\x00\rIDAT\x08\xd7c\xf8\xcf\xc0\xf0\x1f\x00\x05"
                b"\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
            ),
            content_type="image/png",
        ),
    )
    legacy_topic = LegacyTopic.objects.create(
        name="数据中心",
        slug="data-center-legacy",
        description="旧主题",
        accent="#52d5c3",
    )
    page = _published_article(
        owner=owner,
        cover_image=image,
        body=[
            ("markdown", "旧系统正文"),
            (
                "captioned_image",
                {
                    "image": image,
                    "alt_text": "制冷系统图",
                    "caption": "系统示意",
                    "source": "自绘",
                    "width": "normal",
                },
            ),
        ],
    )
    page.topics.add(legacy_topic)
    page.save_revision().publish()
    page.title = "尚未发布的新草稿标题"
    page.body = [("markdown", "尚未发布的新草稿正文")]
    page.save_revision()
    Favorite.objects.create(user=owner, item_type="article", object_id=str(page.pk))

    first = LegacyConverter(actor=owner).run()
    verified = LegacyVerifier().run()
    article = Article.objects.get(legacy_source_id=page.pk)
    first_pk = article.pk

    assert first.critical_count == 0
    assert verified.critical_count == 0
    assert article.status == ContentEntry.Status.PUBLISHED
    assert article.title == "尚未发布的新草稿标题"
    assert article.published_title == "旧文章"
    assert "尚未发布的新草稿正文" in article.body_text
    assert "旧系统正文" in article.published_body_text
    assert article.topics.get().legacy_source_id == legacy_topic.pk
    assert article.published_topics.get().legacy_source_id == legacy_topic.pk
    assert article.published_cover_asset.legacy_source_id == image.pk
    assert article.published_cover_asset.file.name == image.file.name
    body_image = next(
        node for node in article.published_body_json["doc"]["content"] if node["type"] == "image"
    )
    assert body_image["attrs"]["assetId"] == article.published_cover_asset_id
    assert Asset.objects.filter(legacy_source_id=image.pk).count() == 1
    assert Favorite.objects.get(user=owner).object_id == str(article.pk)

    second = LegacyConverter(actor=owner).run()
    article.refresh_from_db()

    assert second.critical_count == 0
    assert article.pk == first_pk
    assert Article.objects.filter(legacy_source_id=page.pk).count() == 1
    assert Topic.objects.filter(legacy_source_id=legacy_topic.pk).count() == 1
    assert LegacyVerifier().run().critical_count == 0


def test_import_command_dry_run_rolls_back_then_execute_and_verify(tmp_path):
    owner = User.objects.create_user("command-owner@example.com", PASSWORD)
    page = _published_article(owner=owner, slug="command-import")
    report_path = tmp_path / "import.json"

    call_command(
        "import_wagtail_content",
        actor_email=owner.email,
        report=str(report_path),
    )

    assert report_path.exists()
    assert not Article.objects.filter(legacy_source_id=page.pk).exists()

    call_command(
        "import_wagtail_content",
        execute=True,
        actor_email=owner.email,
        report=str(report_path),
    )
    call_command("verify_legacy_content", report=str(tmp_path / "verify.json"))

    assert Article.objects.filter(legacy_source_id=page.pk).exists()


def test_import_command_rolls_back_every_write_on_failure(monkeypatch, tmp_path):
    class FailingConverter:
        def __init__(self, *, actor):
            self.actor = actor

        def run(self):
            Topic.objects.create(name="不得残留", slug="must-rollback")
            raise RuntimeError("synthetic conversion failure")

    monkeypatch.setattr(
        "publishing.management.commands.import_wagtail_content.LegacyConverter",
        FailingConverter,
    )

    with pytest.raises(RuntimeError, match="synthetic conversion failure"):
        call_command(
            "import_wagtail_content",
            execute=True,
            report=str(tmp_path / "failed.json"),
        )

    assert not Topic.objects.filter(slug="must-rollback").exists()


def test_verify_command_fails_on_critical_difference(tmp_path):
    owner = User.objects.create_user("difference-owner@example.com", PASSWORD)
    page = _published_article(owner=owner, slug="difference")
    LegacyConverter(actor=owner).run()
    article = Article.objects.get(legacy_source_id=page.pk)
    article.published_title = "被破坏的标题"
    article.save(update_fields={"published_title"})

    with pytest.raises(CommandError, match="核对失败"):
        call_command("verify_legacy_content", report=str(tmp_path / "difference.json"))

    payload = json.loads((tmp_path / "difference.json").read_text(encoding="utf-8"))
    assert any(item["field"] == "published_title" for item in payload["differences"])
