from datetime import date
from unittest.mock import patch

import pytest
from allauth.mfa.models import Authenticator
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from publishing.documents import DocumentValidationError, extract_text, render_document
from publishing.models import Article
from resources.models import Resource, ResourceMirror
from standards.models import Standard
from studio.permissions import ROLE_GROUPS, StudioRole

pytestmark = pytest.mark.django_db
TEST_PASSWORD = "a-safe-test-password"  # noqa: S105


def document(*nodes):
    return {
        "schema_version": 1,
        "doc": {"type": "doc", "content": list(nodes)},
    }


def paragraph(text):
    return {
        "type": "paragraph",
        "content": [{"type": "text", "text": text}],
    }


def callout_node():
    return {
        "type": "callout",
        "attrs": {"variant": "warning", "title": "设计校核"},
        "content": [paragraph("确认冷源冗余配置。")],
    }


def parameter_node():
    return {
        "type": "parameterCard",
        "attrs": {
            "name": "冷冻水供回水温差",
            "value": "6",
            "unit": "℃",
            "note": "设计工况",
        },
    }


def resource(*, title, slug, access_level):
    return Resource.objects.create(
        title=title,
        slug=slug,
        summary="受控资源说明",
        access_level=access_level,
        status=Resource.Status.PUBLISHED,
        published_at=timezone.now(),
    )


def mirror(resource_item, *, code, url):
    return ResourceMirror.objects.create(
        resource=resource_item,
        provider=ResourceMirror.Provider.BAIDU,
        share_url=url,
        extraction_code=code,
    )


def editor_user(*, email, membership=User.MembershipLevel.PENDING):
    user = User.objects.create_user(
        email,
        TEST_PASSWORD,
        membership_level=membership,
    )
    user.groups.add(Group.objects.get(name=ROLE_GROUPS[StudioRole.EDITOR]))
    Authenticator.objects.create(
        user=user,
        type=Authenticator.Type.TOTP,
        data={"secret": "encrypted-test-placeholder"},
    )
    return user


def test_callout_and_parameter_card_validate_render_and_extract_text():
    value = document(callout_node(), parameter_node())

    rendered = render_document(value)
    text = extract_text(value)

    assert 'class="content-callout content-callout-warning"' in rendered
    assert "设计校核" in rendered
    assert "确认冷源冗余配置" in rendered
    assert 'class="content-parameter-card"' in rendered
    assert "冷冻水供回水温差" in rendered
    assert "冷冻水供回水温差 6 ℃ 设计工况" in text


def test_equation_is_server_rendered_to_sanitized_mathml_and_falls_back_safely():
    value = document(
        {"type": "equation", "attrs": {"latex": r"Q = mc\Delta t"}}
    )

    rendered = render_document(value)

    assert 'class="content-equation"' in rendered
    assert "<math" in rendered
    assert "<mi>Q</mi>" in rendered
    assert "script" not in rendered.lower()

    unsafe_source = r"<script>alert('x')</script>"
    with patch("publishing.documents.render.latex_to_mathml", side_effect=ValueError):
        fallback = render_document(
            document({"type": "equation", "attrs": {"latex": unsafe_source}})
        )
    assert "公式暂时无法渲染" in fallback
    assert "<script>" not in fallback
    assert "&lt;script&gt;" in fallback


def test_standard_reference_stores_only_id_and_uses_current_database_record():
    standard = Standard.objects.create(
        code="GB 50174-2017",
        slug="gb-50174-2017",
        title_cn="数据中心设计规范",
        category=Standard.Category.NATIONAL,
        status=Standard.Status.CURRENT,
        effective_on=date(2018, 1, 1),
    )
    value = document(
        {"type": "standardReference", "attrs": {"standardId": standard.pk}}
    )

    first = render_document(value)
    standard.title_cn = "数据中心设计标准（当前记录）"
    standard.save(update_fields={"title_cn", "updated_at"})
    second = render_document(value)

    assert value["doc"]["content"][0]["attrs"] == {"standardId": standard.pk}
    assert "GB 50174-2017" in first
    assert "数据中心设计规范" in first
    assert "数据中心设计标准（当前记录）" in second
    assert standard.get_absolute_url() in second


def test_cloud_resource_links_and_codes_are_resolved_by_membership_level():
    public = resource(
        title="公开计算表",
        slug="public-sheet",
        access_level=Resource.AccessLevel.PUBLIC,
    )
    restricted = resource(
        title="高级会员资料",
        slug="advanced-pack",
        access_level=Resource.AccessLevel.ADVANCED,
    )
    mirror(public, code="open-code", url="https://pan.example.com/public")
    mirror(restricted, code="secret-code", url="https://pan.example.com/restricted")
    public_doc = document(
        {"type": "cloudResource", "attrs": {"resourceId": public.pk}}
    )
    restricted_doc = document(
        {"type": "cloudResource", "attrs": {"resourceId": restricted.pk}}
    )

    anonymous_html = render_document(public_doc)
    locked_html = render_document(restricted_doc)
    trusted = User.objects.create_user(
        "trusted-resource@example.com",
        TEST_PASSWORD,
        membership_level=User.MembershipLevel.TRUSTED,
    )
    trusted_html = render_document(restricted_doc, user=trusted)

    assert "公开计算表" in anonymous_html
    assert "open-code" in anonymous_html
    assert "pan.example.com/public" in anonymous_html
    assert "高级会员资料" not in locked_html
    assert "secret-code" not in locked_html
    assert "pan.example.com/restricted" not in locked_html
    assert "受限网盘资源" in locked_html
    assert "高级会员资料" in trusted_html
    assert "secret-code" in trusted_html
    assert "pan.example.com/restricted" in trusted_html


def test_restricted_resource_secret_never_enters_cached_article_html():
    restricted = resource(
        title="缓存中不能出现的资料",
        slug="cache-secret",
        access_level=Resource.AccessLevel.ADVANCED,
    )
    mirror(restricted, code="never-cache", url="https://pan.example.com/never-cache")
    author = User.objects.create_user("article-author@example.com", TEST_PASSWORD)

    article = Article.objects.create(
        title="资源文章",
        slug="resource-article",
        author=author,
        body_json=document(
            {"type": "cloudResource", "attrs": {"resourceId": restricted.pk}}
        ),
    )

    assert "never-cache" not in article.rendered_html
    assert "pan.example.com/never-cache" not in article.rendered_html
    assert "缓存中不能出现的资料" not in article.rendered_html
    assert "受限网盘资源" in article.rendered_html


def test_editor_preview_resolves_resource_for_current_membership(client):
    restricted = resource(
        title="预览可见资料",
        slug="preview-resource",
        access_level=Resource.AccessLevel.ADVANCED,
    )
    mirror(restricted, code="preview-code", url="https://pan.example.com/preview")
    editor = editor_user(
        email="trusted-editor@example.com",
        membership=User.MembershipLevel.TRUSTED,
    )
    article = Article.objects.create(
        title="预览资源文章",
        slug="preview-resource-article",
        author=editor,
        body_json=document(
            {"type": "cloudResource", "attrs": {"resourceId": restricted.pk}}
        ),
    )
    client.force_login(editor)

    response = client.get(reverse("studio:article_preview", args=(article.pk,)))
    body = response.content.decode()

    assert response.status_code == 200
    assert "预览可见资料" in body
    assert "preview-code" in body
    assert "pan.example.com/preview" in body


@pytest.mark.parametrize(
    "node",
    [
        {"type": "callout", "attrs": {"variant": "danger", "title": "x"}},
        {"type": "equation", "attrs": {"latex": ""}},
        {"type": "standardReference", "attrs": {"standardId": "1"}},
        {"type": "cloudResource", "attrs": {"resourceId": -1}},
        {
            "type": "parameterCard",
            "attrs": {"name": "", "value": "", "unit": "", "note": ""},
        },
        {
            "type": "cloudResource",
            "attrs": {"resourceId": 1},
            "content": [paragraph("不允许的子内容")],
        },
    ],
)
def test_invalid_professional_node_payloads_are_rejected(node):
    with pytest.raises(DocumentValidationError):
        render_document(document(node))


def test_missing_reference_records_degrade_without_crashing():
    rendered = render_document(
        document(
            {"type": "standardReference", "attrs": {"standardId": 999_999}},
            {"type": "cloudResource", "attrs": {"resourceId": 999_999}},
        )
    )

    assert "规范记录 #999999" in rendered
    assert "当前不可用" in rendered
    assert "受限网盘资源" in rendered


def test_reference_search_is_readable_and_never_returns_resource_secrets(client):
    standard = Standard.objects.create(
        code="GB 50736-2012",
        slug="gb-50736-2012",
        title_cn="民用建筑供暖通风与空气调节设计规范",
        category=Standard.Category.NATIONAL,
        status=Standard.Status.CURRENT,
        effective_on=date(2012, 10, 1),
    )
    resource_item = resource(
        title="数据中心冷源计算表",
        slug="cooling-calculation-sheet",
        access_level=Resource.AccessLevel.ADVANCED,
    )
    mirror(
        resource_item,
        code="must-not-leak",
        url="https://pan.example.com/must-not-leak",
    )
    editor = editor_user(email="reference-search@example.com")
    client.force_login(editor)

    standard_response = client.get(
        reverse("studio:api_reference_search"),
        {"kind": "standard", "q": "50736"},
    )
    resource_response = client.get(
        reverse("studio:api_reference_search"),
        {"kind": "resource", "q": "冷源"},
    )

    assert standard_response.status_code == 200
    assert standard_response.json()["items"] == [
        {
            "id": standard.pk,
            "label": "GB 50736-2012",
            "description": "民用建筑供暖通风与空气调节设计规范 · 现行",
        }
    ]
    assert resource_response.status_code == 200
    resource_payload = resource_response.json()["items"]
    assert resource_payload == [
        {
            "id": resource_item.pk,
            "label": "数据中心冷源计算表",
            "description": "高级会员区",
        }
    ]
    encoded = resource_response.content.decode()
    assert "must-not-leak" not in encoded
    assert "pan.example.com" not in encoded
