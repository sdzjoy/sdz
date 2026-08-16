from datetime import date
from pathlib import Path

import pytest
from allauth.mfa.models import Authenticator
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from content.models import ArticleIndexPage, ArticlePage, NoteIndexPage, NotePage
from content.wagtail_hooks import article_listing

pytestmark = pytest.mark.django_db
User = get_user_model()


def section(model):
    return model.objects.get(depth=3)


def publish(parent, page):
    page.live = False
    parent.add_child(instance=page)
    page.save_revision().publish()
    page.refresh_from_db()
    return page


def cms_owner(client, email="cms-owner@example.com"):
    owner = User.objects.create_superuser(email, "a-safe-test-password")
    Authenticator.objects.create(
        user=owner,
        type=Authenticator.Type.TOTP,
        data={"secret": "encrypted-test-placeholder"},
    )
    client.force_login(owner)
    return owner


def test_cms_home_is_an_editorial_workbench_with_real_content(client):
    cms_owner(client)
    article_index = section(ArticleIndexPage)
    draft = ArticlePage(
        title="继续完成液冷设计草稿",
        slug="continue-liquid-cooling-draft",
        summary="后台工作台草稿。",
        published_on=date(2026, 8, 16),
        live=False,
    )
    article_index.add_child(instance=draft)
    draft.save_revision()
    published = publish(
        article_index,
        ArticlePage(
            title="已发布的数据中心气流文章",
            slug="published-airflow-article",
            summary="后台工作台已发布内容。",
            published_on=date(2026, 8, 15),
        ),
    )
    pending_note = NotePage(
        title="待整理的现场随记",
        slug="pending-field-note",
        summary="尚未整理成文章。",
        noted_on=date(2026, 8, 14),
        live=False,
    )
    section(NoteIndexPage).add_child(instance=pending_note)
    pending_note.save_revision()

    response = client.get("/legacy-cms/")
    body = response.content.decode()

    assert response.status_code == 200
    assert "少惰主内容工作台" in body
    assert "新建文章" in body
    assert "继续完成液冷设计草稿" in body
    assert "已发布的数据中心气流文章" in body
    assert "待整理的现场随记" in body
    assert reverse("wagtailadmin_pages:edit", args=(draft.pk,)) in body
    assert published.url in body


def test_workbench_does_not_leak_pages_or_add_actions_without_page_permission(client):
    article_index = section(ArticleIndexPage)
    hidden = ArticlePage(
        title="无权限用户不能看到的草稿",
        slug="permission-hidden-draft",
        summary="权限测试。",
        live=False,
    )
    article_index.add_child(instance=hidden)
    hidden.save_revision()

    staff = User.objects.create_user(
        "limited-staff@example.com",
        "a-safe-test-password",
        is_staff=True,
    )
    staff.user_permissions.add(Permission.objects.get(codename="access_admin"))
    Authenticator.objects.create(
        user=staff,
        type=Authenticator.Type.TOTP,
        data={"secret": "encrypted-test-placeholder"},
    )
    client.force_login(staff)

    response = client.get("/legacy-cms/")
    body = response.content.decode()

    assert response.status_code == 200
    assert "少惰主内容工作台" in body
    assert "无权限用户不能看到的草稿" not in body
    assert "新建文章" not in body
    assert reverse("article_pages:index") not in body


def test_article_listing_exposes_editorial_columns_and_filters():
    column_names = {column.name for column in article_listing.columns}

    assert {
        "status",
        "published_on",
        "project",
        "topics",
        "reading_time",
        "featured",
        "latest_revision_created_at",
    } <= column_names
    assert {
        "live",
        "has_unpublished_changes",
        "project",
        "topics",
        "published_on",
        "featured",
    } <= set(article_listing.list_filter)


def test_article_listing_links_title_directly_to_edit_page(client):
    cms_owner(client)
    article = publish(
        section(ArticleIndexPage),
        ArticlePage(
            title="列表直接编辑文章",
            slug="direct-list-edit",
            summary="文章列表测试。",
            published_on=date(2026, 8, 13),
            body=[("paragraph", "正文")],
        ),
    )
    draft = ArticlePage(
        title="列表筛选时隐藏的草稿",
        slug="filtered-draft",
        summary="文章筛选测试。",
        published_on=date(2026, 8, 12),
        live=False,
    )
    section(ArticleIndexPage).add_child(instance=draft)
    draft.save_revision()

    response = client.get(reverse("article_pages:index"))
    body = response.content.decode()

    assert response.status_code == 200
    assert "列表直接编辑文章" in body
    assert reverse("wagtailadmin_pages:edit", args=(article.pk,)) in body
    assert "1 分钟" in body

    search_response = client.get(reverse("article_pages:index"), {"q": "列表直接编辑"})
    assert search_response.status_code == 200
    assert "列表直接编辑文章" in search_response.content.decode()

    live_response = client.get(reverse("article_pages:index"), {"live": "true"})
    live_body = live_response.content.decode()
    assert live_response.status_code == 200
    assert "列表直接编辑文章" in live_body
    assert "列表筛选时隐藏的草稿" not in live_body


def test_math_preview_requires_admin_mfa_and_post(client):
    preview_url = reverse("editorial_math_preview")

    anonymous = client.post(preview_url, {"latex": "x=1"})
    assert anonymous.status_code == 302
    assert anonymous.url.startswith("/account/login/")

    owner = User.objects.create_superuser("no-mfa@example.com", "a-safe-test-password")
    client.force_login(owner)
    without_mfa = client.post(preview_url, {"latex": "x=1"})
    assert without_mfa.status_code == 302
    assert without_mfa.url == reverse("mfa_index")

    Authenticator.objects.create(
        user=owner,
        type=Authenticator.Type.TOTP,
        data={"secret": "encrypted-test-placeholder"},
    )
    get_response = client.get(preview_url)
    assert get_response.status_code == 405


def test_math_preview_returns_local_mathml_and_safe_errors(client):
    cms_owner(client)
    preview_url = reverse("editorial_math_preview")

    response = client.post(preview_url, {"latex": r"Q=c_p m \Delta T"})
    payload = response.json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert "<math" in payload["html"]
    assert 'display="block"' in payload["html"]
    assert "cdn" not in payload["html"].lower()

    too_long = client.post(preview_url, {"latex": "x" * 10001})
    assert too_long.status_code == 400
    assert too_long.json()["ok"] is False
    assert "公式过长" in too_long.json()["html"]


def test_article_editor_loads_immersive_ui_and_formula_preview_assets(client):
    cms_owner(client)
    article = publish(
        section(ArticleIndexPage),
        ArticlePage(
            title="沉浸式编辑器测试",
            slug="immersive-editor-test",
            summary="检查后台资源。",
            published_on=date(2026, 8, 16),
            body=[("equation", {"latex": "x=1"})],
        ),
    )

    response = client.get(reverse("wagtailadmin_pages:edit", args=(article.pk,)))
    body = response.content.decode()

    assert response.status_code == 200
    assert "js/editorial-admin.js" in body
    assert reverse("editorial_math_preview") in body
    assert "editorial-equation-block" in body
    assert "id_cover_image" in body
    assert 'data-contentpath="body"' in body
    assert 'data-w-kbd-key-value="mod+s"' in body

    script = Path("static/js/editorial-admin.js").read_text(encoding="utf-8")
    assert 'form.querySelector(\'[data-contentpath="body"]\')' in script
    assert 'document.querySelector("#id_body")' not in script


def test_editorial_script_cleans_rich_paste_and_warns_about_external_images():
    script = Path("static/js/editorial-admin.js").read_text(encoding="utf-8")

    assert "ALLOWED_PASTE_TAGS" in script
    assert "DOMParser" in script
    assert "clipboardData" in script
    assert "sanitizePastedHtml" in script
    assert "replayPaste" in script
    assert "外部图片未粘贴" in script
    assert "请使用图片与图注块重新上传" in script
    assert "javascript:" in script
    assert "mso-hide" in script
    assert "aria-live" in script
    assert "hadTables" in script
    assert "表格内容已保留为可编辑行" in script
    assert 'setStatus("dirty", "有未保存修改")' in script
    assert 'editor.dispatchEvent(new Event("input", { bubbles: true }))' in script


def test_article_rich_text_supports_pasted_heading_structure():
    paragraph = dict(ArticlePage.body.field.stream_block.child_blocks)["paragraph"]

    assert {"h2", "h3", "h4"} <= set(paragraph.features)
