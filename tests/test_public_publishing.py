from datetime import date

import pytest
from django.test import override_settings
from django.urls import reverse

from accounts.models import User
from publishing.models import Article, Note, Project, SiteProfile, Tool
from publishing.services import publish_content, save_draft, unpublish_content

pytestmark = pytest.mark.django_db
TEST_PASSWORD = "a-safe-test-password"  # noqa: S105


def document(text):
    return {
        "schema_version": 1,
        "doc": {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": text}],
                }
            ],
        },
    }


def author():
    return User.objects.create_user("public-author@example.com", TEST_PASSWORD)


def publish(item, actor):
    return publish_content(item, expected_version=item.version, actor=actor)


@pytest.mark.parametrize(
    ("path", "heading", "empty_state"),
    [
        ("/articles/", "文章", "文章正在逐篇整理"),
        ("/projects/", "项目", "项目记录正在脱敏整理"),
        ("/notes/", "随记", "第一批随记正在整理"),
        ("/tools/", "工具", "工具目录正在建立"),
    ],
)
def test_public_indexes_keep_existing_editorial_urls_and_empty_states(
    client, path, heading, empty_state
):
    response = client.get(path)
    body = response.content.decode()

    assert response.status_code == 200
    assert heading in body
    assert empty_state in body
    assert 'class="index-masthead"' in body
    assert response["Cache-Control"] == "public, max-age=60"
    assert response["Vary"] == "Cookie"


def test_public_page_reads_only_frozen_snapshot_after_draft_changes(client):
    actor = author()
    article = Article.objects.create(
        title="线上文章",
        slug="public-snapshot",
        summary="线上摘要",
        body_json=document("线上正文"),
        published_on=date(2026, 8, 17),
        author=actor,
    )
    article = publish(article, actor)
    article = save_draft(
        article,
        expected_version=article.version,
        actor=actor,
        title="尚未发布的新标题",
        slug="unpublished-new-slug",
        summary="尚未发布的新摘要",
        body_json=document("尚未发布的新正文"),
    )

    detail = client.get("/articles/public-snapshot/")
    index = client.get("/articles/")
    document_body = detail.content.decode()

    assert detail.status_code == 200
    assert "线上文章" in document_body
    assert "线上摘要" in document_body
    assert "线上正文" in document_body
    assert "尚未发布" not in document_body
    assert "线上文章" in index.content.decode()
    assert "尚未发布的新标题" not in index.content.decode()
    assert client.get("/articles/unpublished-new-slug/").status_code == 404


def test_drafts_and_unpublished_content_are_not_public_or_discoverable(client):
    actor = author()
    draft = Article.objects.create(
        title="内部草稿",
        slug="internal-draft",
        body_json=document("内部正文"),
        author=actor,
    )
    published = publish(
        Article.objects.create(
            title="暂时公开",
            slug="then-unpublished",
            body_json=document("曾经公开"),
            author=actor,
        ),
        actor,
    )
    unpublish_content(published, expected_version=published.version, actor=actor)

    assert client.get(draft.get_absolute_url()).status_code == 404
    assert client.get("/articles/then-unpublished/").status_code == 404
    assert "内部草稿" not in client.get("/articles/").content.decode()
    assert "then-unpublished" not in client.get("/sitemap.xml").content.decode()


def test_all_detail_types_keep_urls_metadata_breadcrumbs_and_timeline(client):
    actor = author()
    project = publish(
        Project.objects.create(
            title="数据中心项目",
            slug="dc-project",
            summary="项目摘要",
            body_json=document("项目正文"),
            project_status=Project.ProjectStatus.ACTIVE,
            author=actor,
        ),
        actor,
    )
    article = publish(
        Article.objects.create(
            title="项目文章",
            slug="project-article",
            summary="文章摘要",
            body_json=document("文章正文"),
            parent_project_id=project.pk,
            author=actor,
        ),
        actor,
    )
    note = publish(
        Note.objects.create(
            title="现场随记",
            slug="field-note",
            summary="随记摘要",
            body_json=document("随记正文"),
            promoted_article_id=article.pk,
            author=actor,
        ),
        actor,
    )
    tool = publish(
        Tool.objects.create(
            title="计算工具",
            slug="calc-tool",
            summary="工具摘要",
            body_json=document("工具正文"),
            service_url="https://hvac.sdzjoy.com/",
            tool_status=Tool.ToolStatus.ONLINE,
            author=actor,
        ),
        actor,
    )

    for item in (project, article, note, tool):
        response = client.get(item.get_absolute_url())
        body = response.content.decode()
        assert response.status_code == 200
        assert item.published_title in body
        assert 'aria-label="面包屑"' in body
        assert '<link rel="canonical"' in body

    project_body = client.get(project.get_absolute_url()).content.decode()
    note_body = client.get(note.get_absolute_url()).content.decode()
    tool_body = client.get(tool.get_absolute_url()).content.decode()
    assert "进行中" in project_body
    assert "项目文章" in project_body
    assert "这条随记已整理为" in note_body
    assert "https://hvac.sdzjoy.com/" in tool_body


def test_about_uses_site_profile_and_server_rendered_document(client):
    profile = SiteProfile(
        about_intro="数据中心暖通设计与工程实践。",
        about_body_json=document("关于正文"),
    )
    profile.save()

    response = client.get(reverse("publishing:about"))
    body = response.content.decode()

    assert response.status_code == 200
    assert "数据中心暖通设计与工程实践。" in body
    assert "关于正文" in body
    assert 'aria-label="面包屑"' in body


@override_settings(PUBLIC_SITE_ORIGIN="https://sdzjoy.com")
def test_feed_sitemap_canonical_and_structured_data_use_published_snapshot(client):
    actor = author()
    article = publish(
        Article.objects.create(
            title="公开发现文章",
            slug="discoverable",
            summary="用于 RSS 和站点地图。",
            body_json=document("正文"),
            published_on=date(2026, 8, 15),
            author=actor,
        ),
        actor,
    )
    save_draft(
        article,
        expected_version=article.version,
        actor=actor,
        title="不能进入发现入口的新草稿",
        slug="hidden-discovery-draft",
        summary="未发布",
        body_json=document("未发布正文"),
    )

    feed = client.get("/feeds/articles.xml").content.decode()
    sitemap = client.get("/sitemap.xml").content.decode()
    detail = client.get("/articles/discoverable/").content.decode()

    assert "公开发现文章" in feed
    assert "不能进入发现入口的新草稿" not in feed
    assert "/articles/discoverable/" in sitemap
    assert "hidden-discovery-draft" not in sitemap
    assert '<link rel="canonical" href="https://sdzjoy.com/articles/discoverable/">' in detail
    assert '<meta property="og:type" content="article">' in detail
    assert '"@type":"BlogPosting"' in detail


def test_authenticated_public_page_is_never_shared_cacheable(client):
    actor = author()
    article = publish(
        Article.objects.create(
            title="会员访问页面",
            slug="member-cache",
            body_json=document("正文"),
            author=actor,
        ),
        actor,
    )
    client.force_login(actor)

    response = client.get(article.get_absolute_url())

    assert response.status_code == 200
    assert response["Cache-Control"] == "private, no-store"
    assert "Cookie" in response["Vary"]
