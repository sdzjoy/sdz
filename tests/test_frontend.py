from datetime import date
from pathlib import Path

import pytest
from django.contrib.staticfiles import finders
from django.test import override_settings

from accounts.models import User
from publishing.models import Article, Project
from publishing.services import publish_content

pytestmark = pytest.mark.django_db
TEST_PASSWORD = "a-safe-test-password"  # noqa: S105


def publish_entry(entry, actor):
    return publish_content(entry, expected_version=entry.version, actor=actor)


def test_homepage_has_honest_empty_state_and_accessible_site_shell(client):
    response = client.get("/")
    document = response.content.decode()

    assert response.status_code == 200
    assert "首发内容尚未公开" in document
    assert "即将上线" not in document
    assert 'class="skip-link"' in document
    assert 'id="main-content"' in document
    assert 'aria-label="主导航"' in document
    assert 'class="theme-toggle"' in document
    assert 'href="https://hvac.sdzjoy.com/"' in document
    assert "研究工程" in document
    assert "少惰主从" in document
    assert 'href="/static/css/editorial.css"' in document


def test_brand_assets_are_discoverable():
    assert finders.find("css/site.css")
    editorial_path = finders.find("css/editorial.css")
    assert editorial_path
    assert finders.find("js/site.js")
    assert finders.find("img/mark.svg")

    editorial_css = Path(editorial_path).read_text(encoding="utf-8")
    assert "--type-display" in editorial_css
    assert "--type-body" in editorial_css
    assert 'font-family: var(--font-sans);' in editorial_css


def test_signup_uses_the_same_editorial_system_as_the_public_site(client):
    response = client.get("/account/signup/")
    document = response.content.decode()

    assert response.status_code == 200
    assert "注册少惰主账号" in document
    assert "注册后需完成验证或审核" in document
    assert 'class="auth-layout"' in document
    assert 'href="/static/css/editorial.css"' in document
    assert '<meta name="theme-color" content="#faf9f5">' in document


@pytest.mark.parametrize(
    ("path", "heading", "empty_state"),
    [
        ("/articles/", "文章", "文章正在逐篇整理"),
        ("/projects/", "项目", "项目记录正在脱敏整理"),
        ("/notes/", "随记", "第一批随记正在整理"),
        ("/tools/", "工具", "工具目录正在建立"),
    ],
)
def test_content_indexes_use_the_editorial_masthead(client, path, heading, empty_state):
    response = client.get(path)
    document = response.content.decode()

    assert response.status_code == 200
    assert heading in document
    assert empty_state in document
    assert 'class="index-masthead"' in document


def test_homepage_only_surfaces_published_content(client):
    actor = User.objects.create_user("homepage-author@example.com", TEST_PASSWORD)
    publish_entry(
        Project.objects.create(
            title="已公开项目",
            slug="public-project",
            summary="真实公开内容。",
            started_on=date(2026, 8, 1),
            featured=True,
            author=actor,
        ),
        actor,
    )
    Project.objects.create(
        title="未公开项目",
        slug="draft-project",
        summary="不应出现在首页。",
        started_on=date(2026, 8, 2),
        author=actor,
    )

    response = client.get("/")
    document = response.content.decode()

    assert "已公开项目" in document
    assert "未公开项目" not in document
    assert "首发内容尚未公开" not in document


@override_settings(PUBLIC_SITE_ORIGIN="https://sdzjoy.com")
def test_public_pages_include_canonical_open_graph_and_structured_data(client):
    response = client.get("/articles/")
    document = response.content.decode()

    assert '<link rel="canonical" href="https://sdzjoy.com/articles/">' in document
    assert '<meta property="og:url" content="https://sdzjoy.com/articles/">' in document
    assert 'type="application/ld+json"' in document
    assert '"@type":"WebSite"' in document


@override_settings(
    ALLOWED_HOSTS=["www.sdzjoy.com", "sdzjoy.com"],
    PUBLIC_SITE_ORIGIN="https://sdzjoy.com",
    WWW_REDIRECT_HOST="www.sdzjoy.com",
)
def test_www_redirect_is_permanent_and_preserves_path_and_query(client):
    response = client.get("/articles/?page=2", HTTP_HOST="www.sdzjoy.com")

    assert response.status_code == 308
    assert response["Location"] == "https://sdzjoy.com/articles/?page=2"


def test_rss_and_sitemap_exclude_drafts(client):
    actor = User.objects.create_user("feed-author@example.com", TEST_PASSWORD)
    published = publish_entry(
        Article.objects.create(
            title="公开文章",
            slug="published-article",
            summary="应出现在公开发现入口。",
            published_on=date(2026, 8, 15),
            author=actor,
        ),
        actor,
    )
    Article.objects.create(
        title="内部草稿",
        slug="internal-draft",
        summary="不能被发现。",
        published_on=date(2026, 8, 16),
        author=actor,
    )

    feed = client.get("/feeds/articles.xml").content.decode()
    sitemap = client.get("/sitemap.xml").content.decode()

    assert published.published_title in feed
    assert "内部草稿" not in feed
    assert published.published_slug in sitemap
    assert "internal-draft" not in sitemap


def test_article_uses_article_metadata(client):
    actor = User.objects.create_user("metadata-author@example.com", TEST_PASSWORD)
    article = publish_entry(
        Article.objects.create(
            title="结构化文章",
            slug="structured-article",
            summary="用于检查文章元数据。",
            published_on=date(2026, 8, 15),
            author=actor,
        ),
        actor,
    )

    document = client.get(article.get_absolute_url()).content.decode()

    assert '<meta property="og:type" content="article">' in document
    assert '"@type":"BlogPosting"' in document
    assert "用于检查文章元数据。" in document
