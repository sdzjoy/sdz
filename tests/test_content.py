from datetime import date

import pytest
from django.db.models.deletion import ProtectedError
from django.test import RequestFactory
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
