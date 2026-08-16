import io
import json

import pytest
from allauth.mfa.models import Authenticator
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from PIL import Image, PngImagePlugin

from accounts.models import User
from publishing.documents import DocumentValidationError, extract_text, render_document
from publishing.models import Article, Asset
from publishing.uploads import ImageUploadError, prepare_image
from studio.models import AuditEvent
from studio.permissions import ROLE_GROUPS, StudioRole
from studio.services.assets import upload_image_asset

pytestmark = pytest.mark.django_db
TEST_PASSWORD = "a-safe-test-password"  # noqa: S105


def backend_user(role=StudioRole.EDITOR, email="asset-editor@example.com"):
    user = User.objects.create_user(email, TEST_PASSWORD)
    user.groups.add(Group.objects.get(name=ROLE_GROUPS[role]))
    Authenticator.objects.create(
        user=user,
        type=Authenticator.Type.TOTP,
        data={"secret": "encrypted-test-placeholder"},
    )
    return user


def image_bytes(*, size=(24, 16), image_format="PNG", metadata=False):
    output = io.BytesIO()
    image = Image.new("RGB", size, color=(38, 94, 121))
    if image_format == "PNG" and metadata:
        info = PngImagePlugin.PngInfo()
        info.add_text("Author", "should be removed")
        image.save(output, format="PNG", pnginfo=info)
    else:
        image.save(output, format=image_format)
    return output.getvalue()


def uploaded_png(name="机房图片.php.png", *, metadata=False):
    return SimpleUploadedFile(
        name,
        image_bytes(metadata=metadata),
        content_type="application/octet-stream",
    )


def image_document(asset):
    return {
        "schema_version": 1,
        "doc": {
            "type": "doc",
            "content": [
                {
                    "type": "image",
                    "attrs": {
                        "assetId": asset.pk,
                        "src": asset.file.url,
                        "alt": "冷机房设备照片",
                        "title": "设备布置",
                        "width": asset.width,
                        "height": asset.height,
                    },
                }
            ],
        },
    }


def article_payload(document):
    return {
        "intent": "autosave",
        "title": "带图片的文章",
        "slug": "with-image",
        "summary": "",
        "body_json": document,
        "version": 0,
        "featured": False,
        "published_on": "2026-08-17",
        "reading_minutes": None,
        "parent_project": None,
        "topics": [],
    }


def test_image_upload_validates_reencodes_and_uses_random_filename(client, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    editor = backend_user()
    client.force_login(editor)

    response = client.post(
        reverse("studio:api_asset_upload"),
        {"image": uploaded_png(metadata=True)},
    )
    asset = Asset.objects.get()

    assert response.status_code == 201
    assert asset.mime_type == "image/png"
    assert asset.width == 24
    assert asset.height == 16
    assert asset.original_name == "机房图片.php.png"
    assert "机房图片" not in asset.file.name
    assert asset.file.name.endswith(".png")
    assert len(asset.sha256) == 64
    with Image.open(asset.file.path) as normalized:
        assert "Author" not in normalized.info
    assert AuditEvent.objects.filter(action=AuditEvent.Action.ASSET_UPLOAD).exists()


def test_invalid_or_oversized_image_is_rejected_without_asset(client, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    editor = backend_user()
    client.force_login(editor)

    invalid = client.post(
        reverse("studio:api_asset_upload"),
        {"image": SimpleUploadedFile("fake.jpg", b"<script>not an image</script>")},
    )

    assert invalid.status_code == 400
    assert invalid.json()["code"] == "invalid_image"
    assert Asset.objects.count() == 0


def test_pixel_limit_is_checked_before_image_is_saved(monkeypatch):
    monkeypatch.setattr("publishing.uploads.MAX_IMAGE_PIXELS", 100)

    with pytest.raises(ImageUploadError) as error:
        prepare_image(
            SimpleUploadedFile(
                "large.png",
                image_bytes(size=(11, 10)),
                content_type="image/png",
            )
        )

    assert error.value.code == "image_dimensions"


def test_asset_upload_requires_editor_role_and_csrf(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    resource_admin = backend_user(
        StudioRole.RESOURCE_ADMIN,
        email="asset-resource@example.com",
    )
    role_client = Client()
    role_client.force_login(resource_admin)
    assert role_client.post(
        reverse("studio:api_asset_upload"),
        {"image": uploaded_png()},
    ).status_code == 403

    editor = backend_user(email="asset-csrf@example.com")
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(editor)
    assert csrf_client.post(
        reverse("studio:api_asset_upload"),
        {"image": uploaded_png()},
    ).status_code == 403


def test_asset_library_searches_images(client, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    editor = backend_user()
    first = upload_image_asset(uploaded_png("冷源机房.png"), actor=editor)
    upload_image_asset(uploaded_png("气流组织.png"), actor=editor)
    client.force_login(editor)

    response = client.get(reverse("studio:assets"), {"q": "冷源"})
    body = response.content.decode()

    assert response.status_code == 200
    assert first.title in body
    assert "气流组织" not in body
    assert "复制地址" in body


def test_referenced_asset_cannot_be_deleted(client, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    editor = backend_user()
    asset = upload_image_asset(uploaded_png(), actor=editor)
    Article.objects.create(
        title="引用素材的文章",
        slug="asset-reference",
        author=editor,
        body_json=image_document(asset),
    )
    client.force_login(editor)

    response = client.post(reverse("studio:api_asset_delete", args=(asset.pk,)))
    asset.refresh_from_db()

    assert response.status_code == 409
    assert response.json()["code"] == "asset_in_use"
    assert response.json()["references"][0]["label"] == "引用素材的文章"
    assert "草稿正文" in response.json()["references"][0]["locations"]
    assert asset.deleted_at is None


def test_unreferenced_asset_is_soft_deleted_and_audited(client, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    editor = backend_user()
    asset = upload_image_asset(uploaded_png(), actor=editor)
    client.force_login(editor)

    response = client.post(reverse("studio:api_asset_delete", args=(asset.pk,)))
    asset.refresh_from_db()

    assert response.status_code == 200
    assert asset.deleted_at is not None
    assert asset.file.storage.exists(asset.file.name)
    assert AuditEvent.objects.filter(
        action=AuditEvent.Action.ASSET_DELETE,
        object_id=str(asset.pk),
    ).exists()


def test_article_api_rejects_missing_asset_and_mismatched_internal_url(
    client,
    settings,
    tmp_path,
):
    settings.MEDIA_ROOT = tmp_path
    editor = backend_user()
    client.force_login(editor)
    asset = upload_image_asset(uploaded_png(), actor=editor)
    missing = image_document(asset)
    missing["doc"]["content"][0]["attrs"].update(
        {"assetId": 999, "src": "/media/assets/missing.png"}
    )

    response = client.post(
        reverse("studio:api_article_create"),
        json.dumps(article_payload(missing)),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "不存在或已删除" in response.json()["fields"]["body_json"][0]

    mismatched = image_document(asset)
    mismatched["doc"]["content"][0]["attrs"]["src"] = "/media/assets/another.png"
    response = client.post(
        reverse("studio:api_article_create"),
        json.dumps(article_payload(mismatched)),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "地址与素材记录不一致" in response.json()["fields"]["body_json"][0]


def test_image_document_renders_safe_figure_and_alt_text(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    editor = backend_user()
    asset = upload_image_asset(uploaded_png(), actor=editor)
    document = image_document(asset)

    rendered = render_document(document)

    assert f'src="{asset.file.url}"' in rendered
    assert 'loading="lazy"' in rendered
    assert "冷机房设备照片" in extract_text(document)
    unsafe = image_document(asset)
    unsafe["doc"]["content"][0]["attrs"]["src"] = "https://attacker.example/a.png"
    with pytest.raises(DocumentValidationError):
        render_document(unsafe)
