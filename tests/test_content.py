from datetime import date
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.deletion import ProtectedError
from django.test import RequestFactory
from wagtail.documents import get_document_model
from wagtail.images import get_image_model

from content.models import (
    AboutPage,
    ArticleIndexPage,
    ArticlePage,
    NoteIndexPage,
    NotePage,
    ProjectIndexPage,
    ProjectPage,
    ToolIndexPage,
    ToolPage,
)
from content.templatetags.content_tags import safe_markdown
from core.models import HomePage

pytestmark = pytest.mark.django_db


def section(model):
    return model.objects.get(depth=3)


def publish(parent, page):
    page.live = False
    parent.add_child(instance=page)
    revision = page.save_revision()
    revision.publish()
    page.refresh_from_db()
    return page, revision


def test_section_pages_are_seeded_under_homepage():
    home = HomePage.objects.get(depth=2)

    assert set(home.get_children().values_list("slug", flat=True)) == {
        "about",
        "articles",
        "notes",
        "projects",
        "tools",
    }
    assert AboutPage.objects.filter(depth=3, live=True).exists()


def test_draft_article_is_not_listed_publicly(client):
    article_index = section(ArticleIndexPage)
    draft = ArticlePage(
        title="仅后台可见的草稿",
        slug="private-draft",
        summary="这篇内容尚未发布。",
        published_on=date(2026, 8, 15),
        live=False,
    )
    article_index.add_child(instance=draft)
    draft.save_revision()

    response = client.get(article_index.url)

    assert response.status_code == 200
    assert "仅后台可见的草稿" not in response.content.decode()
    request = RequestFactory().get(article_index.url)
    assert list(article_index.get_context(request)["articles"]) == []


def test_published_article_can_be_rolled_back_to_an_earlier_revision():
    article, first_revision = publish(
        section(ArticleIndexPage),
        ArticlePage(
            title="第一版标题",
            slug="revision-test",
            summary="第一版摘要",
            published_on=date(2026, 8, 10),
            body=[("markdown", "第一版正文")],
        ),
    )
    article.title = "第二版标题"
    article.summary = "第二版摘要"
    article.body = [("markdown", "第二版正文")]
    article.save_revision().publish()

    first_revision.as_object().save_revision().publish()
    article.refresh_from_db()

    assert article.title == "第一版标题"
    assert article.summary == "第一版摘要"
    assert article.body[0].block_type == "markdown"
    assert article.body[0].value == "第一版正文"


def test_referenced_project_cannot_be_deleted():
    project, _ = publish(
        section(ProjectIndexPage),
        ProjectPage(
            title="数据中心冷却项目",
            slug="cooling-project",
            summary="用于验证引用保护。",
            started_on=date(2026, 6, 1),
        ),
    )
    publish(
        section(ArticleIndexPage),
        ArticlePage(
            title="项目复盘",
            slug="project-review",
            summary="文章引用了这个项目。",
            published_on=date(2026, 8, 1),
            project=project,
        ),
    )

    with pytest.raises(ProtectedError):
        project.delete()


def test_project_timeline_combines_related_content_in_date_order():
    project, _ = publish(
        section(ProjectIndexPage),
        ProjectPage(
            title="机房气流组织实验",
            slug="airflow-lab",
            summary="汇总文章、随记和工具。",
            started_on=date(2026, 1, 1),
        ),
    )
    article, _ = publish(
        section(ArticleIndexPage),
        ArticlePage(
            title="实验总结",
            slug="airflow-summary",
            summary="形成完整结论。",
            published_on=date(2026, 8, 12),
            project=project,
        ),
    )
    note, _ = publish(
        section(NoteIndexPage),
        NotePage(
            title="现场随记",
            slug="airflow-note",
            summary="记录一次现场测量。",
            noted_on=date(2026, 8, 15),
            project=project,
            promoted_article=article,
        ),
    )
    tool, _ = publish(
        section(ToolIndexPage),
        ToolPage(
            title="风量换算工具",
            slug="airflow-tool",
            summary="辅助实验计算。",
            launched_on=date(2026, 8, 8),
            project=project,
        ),
    )

    project.refresh_from_db()
    timeline = project.timeline

    assert [(item["kind"], item["page"].pk) for item in timeline] == [
        ("note", note.pk),
        ("article", article.pk),
        ("tool", tool.pk),
    ]
    assert note.promoted_article == article


def test_markdown_disables_raw_html_and_unsafe_urls():
    rendered = str(
        safe_markdown(
            "<script>alert('xss')</script>\n\n[危险链接](javascript:alert('xss'))"
        )
    )

    assert "<script" not in rendered.lower()
    assert 'href="javascript:' not in rendered.lower()
    assert "危险链接" in rendered


def test_article_reading_time_is_estimated_unless_manually_overridden():
    article = ArticlePage(
        title="自动阅读时间",
        summary="验证自动估算。",
        body=[("markdown", "暖通设计" * 176)],
    )

    assert article.reading_minutes is None
    assert article.estimated_reading_minutes == 3
    assert article.effective_reading_minutes == 3

    article.reading_minutes = 12
    assert article.effective_reading_minutes == 12


def test_article_references_merge_same_source_and_keep_cited_locations():
    common = {
        "kind": "standard",
        "identifier": "GB 50736",
        "title_zh": "民用建筑供暖通风与空气调节设计规范",
        "title_en": "",
        "edition": "2012",
        "pages": "",
        "excerpt": "",
        "organization": "",
        "source_url": "https://example.com/gb50736",
        "accessed_on": None,
        "editor_note": "后台私有备注",
    }
    article = ArticlePage(
        title="结构化引用",
        summary="验证引用去重。",
        body=[
            ("reference", {**common, "clause": "4.1.1"}),
            ("paragraph", "正文"),
            ("reference", {**common, "clause": "4.1.2"}),
            ("reference", {**common, "clause": "4.1.1"}),
        ],
    )

    assert len(article.reference_entries) == 1
    assert article.reference_entries[0]["clauses"] == ["4.1.1", "4.1.2"]
    assert "editor_note" not in article.reference_entries[0]


def test_article_editor_keeps_writing_fields_in_content_and_metadata_in_settings():
    content_field_names = {
        panel.field_name
        for panel in ArticlePage.content_panels
        if hasattr(panel, "field_name")
    }
    settings_children = ArticlePage.settings_panels[0].children
    setting_field_names = {panel.field_name for panel in settings_children}

    assert {"summary", "cover_image", "body"} <= content_field_names
    assert "published_on" not in content_field_names
    assert {"published_on", "project", "topics", "featured", "reading_minutes"} <= (
        setting_field_names
    )


def test_article_cover_image_is_optional():
    image_model = get_image_model()

    assert ArticlePage._meta.get_field("cover_image").related_model is image_model
    assert ArticlePage._meta.get_field("cover_image").null is True


def test_article_frontend_renders_professional_blocks_cover_and_bibliography(client):
    image = get_image_model().objects.create(
        title="冷却系统示意图",
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
    document = get_document_model().objects.create(
        title="调试记录",
        file=SimpleUploadedFile(
            "commissioning.txt", b"commissioning record", content_type="text/plain"
        ),
    )
    reference = {
        "kind": "standard",
        "identifier": "GB 50736-2012",
        "title_zh": "民用建筑供暖通风与空气调节设计规范",
        "title_en": "Design code for heating ventilation and air conditioning",
        "edition": "2012",
        "clause": "4.1.1",
        "pages": "附录 A",
        "excerpt": "室外空气计算参数。",
        "organization": "住房和城乡建设部",
        "source_url": "https://example.com/gb50736",
        "accessed_on": date(2026, 8, 16),
        "editor_note": "不会出现在前台",
    }
    article, _ = publish(
        section(ArticleIndexPage),
        ArticlePage(
            title="专业文章前台排版",
            slug="professional-article-layout",
            summary="覆盖公式、表格、参数、图片、附件和参考资料。",
            published_on=date(2026, 8, 16),
            cover_image=image,
            body=[
                ("section_heading", {"level": "h2", "text": "设计条件"}),
                ("paragraph", "<p>正文包含 <strong>工程结论</strong>。</p>"),
                (
                    "callout",
                    {"kind": "experience", "title": "工程经验", "content": "避免短路。"},
                ),
                (
                    "equation",
                    {
                        "latex": r"Q = c_p m \Delta T",
                        "number": "3-1",
                        "caption": "冷量平衡式",
                        "variables": [
                            {"symbol": "Q", "meaning": "冷量", "unit": "kW"}
                        ],
                    },
                ),
                (
                    "data_table",
                    {
                        "title": "设计参数表",
                        "table": {
                            "data": [["参数", "数值"], ["送风温度", "18 ℃"]],
                            "first_row_is_table_header": True,
                            "first_col_is_header": False,
                        },
                        "units": "温度为摄氏度",
                        "source": "设计计算书",
                        "notes": "校核工况。",
                    },
                ),
                (
                    "parameter_card",
                    {
                        "title": "关键参数",
                        "items": [
                            {"name": "送风温度", "value": "18", "unit": "℃", "note": ""}
                        ],
                    },
                ),
                (
                    "captioned_image",
                    {
                        "image": image,
                        "alt_text": "数据中心冷却系统示意",
                        "caption": "图 1 冷却系统",
                        "source": "少惰主",
                        "width": "wide",
                    },
                ),
                (
                    "attachment",
                    {
                        "document": document,
                        "display_name": "调试记录下载",
                        "version": "V1.0",
                        "description": "现场调试原始记录。",
                    },
                ),
                ("reference", reference),
                ("reference", {**reference, "clause": "4.1.2"}),
            ],
        ),
    )

    response = client.get(article.url)
    body = response.content.decode()

    assert response.status_code == 200
    assert 'class="article-masthead"' in body
    assert 'class="article-cover"' in body
    assert 'class="article-reading-area"' in body
    assert 'class="callout callout--experience"' in body
    assert 'class="engineering-equation"' in body
    assert 'class="engineering-table"' in body
    assert "<table" in body
    assert "{'data':" not in body
    assert 'class="parameter-card"' in body
    assert 'class="content-image content-image--wide"' in body
    assert 'class="attachment-card"' in body
    assert body.count('class="article-reference"') == 1
    assert "4.1.1、4.1.2" in body
    assert "编辑备注" not in body
    assert "不会出现在前台" not in body


def test_old_article_without_cover_or_professional_blocks_still_renders(client):
    article, _ = publish(
        section(ArticleIndexPage),
        ArticlePage(
            title="旧版文章继续可用",
            slug="legacy-article-still-renders",
            summary="没有封面和专业内容块。",
            published_on=date(2026, 8, 1),
            body=[("heading", "旧版标题"), ("markdown", "旧版 **正文**")],
        ),
    )

    response = client.get(article.url)
    body = response.content.decode()

    assert response.status_code == 200
    assert "旧版文章继续可用" in body
    assert "旧版" in body
    assert "正文" in body
    assert 'class="article-cover"' not in body
    assert 'class="article-references"' not in body


def test_editorial_css_scopes_wide_equations_and_tables_to_local_scroll():
    css = Path("static/css/editorial.css").read_text(encoding="utf-8")

    assert ".engineering-equation__formula" in css
    assert ".engineering-table__scroll" in css
    assert "overflow-x: auto" in css
    assert ".content-image--wide" in css
    assert "@media (max-width: 680px)" in css
