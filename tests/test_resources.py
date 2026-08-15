import io

import pytest
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from django.utils import timezone
from openpyxl import Workbook

from accounts.models import User
from resources.admin import ResourceAdmin
from resources.imports import confirm_import, preview_import
from resources.models import (
    ImportBatch,
    ImportRow,
    Resource,
    ResourceMirror,
    ResourceVersion,
)

pytestmark = pytest.mark.django_db


RESTRICTED_TITLE = "高级机房气流组织资料"
RESTRICTED_LINK = "https://pan.example.test/s/restricted-airflow"
RESTRICTED_CODE = "H2X9"


def member(level, email):
    return User.objects.create_user(
        email=email,
        membership_level=level,
        is_active=True,
    )


def published_resource(slug, title, level=Resource.AccessLevel.PUBLIC):
    return Resource.objects.create(
        slug=slug,
        title=title,
        summary=f"{title}的完整说明。",
        access_level=level,
        copyright_status=Resource.CopyrightStatus.AUTHORIZED,
        copyright_note="仅限获准范围使用。",
        status=Resource.Status.PUBLISHED,
        published_at=timezone.now(),
    )


def active_mirror(resource, *, link=RESTRICTED_LINK, code=RESTRICTED_CODE, provider="baidu"):
    return ResourceMirror.objects.create(
        resource=resource,
        provider=provider,
        share_url=link,
        extraction_code=code,
        last_verified_at=timezone.now(),
    )


def test_l0_and_l1_cannot_discover_l2_record_in_page_api_search_cache_or_error(client):
    public = published_resource("public-tool", "公开计算工具")
    restricted = published_resource(
        "advanced-airflow",
        RESTRICTED_TITLE,
        Resource.AccessLevel.ADVANCED,
    )
    active_mirror(restricted)
    l1 = member(User.MembershipLevel.MEMBER, "member@example.com")
    client.force_login(l1)

    listing = client.get("/resources/")
    search = client.get("/resources/?q=高级机房")
    detail = client.get(restricted.get_absolute_url())
    api = client.get(f"/resources/api/{restricted.slug}/")
    combined = b" ".join((listing.content, search.content, detail.content, api.content)).decode()

    assert public.title in listing.content.decode()
    assert listing.status_code == 200
    assert search.status_code == 200
    assert detail.status_code == 404
    assert api.status_code == 404
    assert RESTRICTED_TITLE not in combined
    assert RESTRICTED_LINK not in combined
    assert RESTRICTED_CODE not in combined
    assert listing["Cache-Control"] == "private, no-store"
    assert "Cookie" in listing["Vary"]
    assert api["Cache-Control"] == "private, no-store"


def test_l2_can_access_advanced_resource_and_active_mirror(client):
    restricted = published_resource(
        "advanced-cooling",
        RESTRICTED_TITLE,
        Resource.AccessLevel.ADVANCED,
    )
    active_mirror(restricted)
    l2 = member(User.MembershipLevel.TRUSTED, "trusted@example.com")
    client.force_login(l2)

    detail = client.get(restricted.get_absolute_url())
    api = client.get(f"/resources/api/{restricted.slug}/")

    assert detail.status_code == 200
    assert RESTRICTED_LINK in detail.content.decode()
    assert RESTRICTED_CODE in detail.content.decode()
    assert api.json()["mirrors"][0]["share_url"] == RESTRICTED_LINK
    assert api["X-Robots-Tag"] == "noindex, nofollow"


def test_membership_downgrade_immediately_revokes_old_session(client):
    restricted = published_resource(
        "downgrade-check",
        RESTRICTED_TITLE,
        Resource.AccessLevel.ADVANCED,
    )
    active_mirror(restricted)
    user = member(User.MembershipLevel.TRUSTED, "downgrade@example.com")
    client.force_login(user)

    assert client.get(restricted.get_absolute_url()).status_code == 200
    User.objects.filter(pk=user.pk).update(membership_level=User.MembershipLevel.MEMBER)

    denied = client.get(restricted.get_absolute_url())
    assert denied.status_code == 404
    assert RESTRICTED_LINK not in denied.content.decode()
    assert RESTRICTED_CODE not in denied.content.decode()


def test_failed_mirror_is_hidden_while_other_mirror_remains_available(client):
    resource = published_resource("multi-mirror", "多镜像测试资源")
    failed = active_mirror(
        resource,
        link="https://pan.example.test/s/failed",
        code="FAIL",
    )
    failed.status = ResourceMirror.Status.FAILED
    failed.failure_note = "分享已失效。"
    failed.save()
    active = active_mirror(
        resource,
        link="https://drive.example.test/s/working",
        code="GOOD",
        provider=ResourceMirror.Provider.PCLOUD,
    )

    document = client.get(resource.get_absolute_url()).content.decode()

    assert active.share_url in document
    assert active.extraction_code in document
    assert failed.share_url not in document
    assert failed.extraction_code not in document


def test_resource_admin_can_publish_new_record_with_audit_timestamp():
    actor = member(User.MembershipLevel.OWNER, "admin-form@example.com")
    actor.is_staff = True
    actor.is_superuser = True
    actor.save(update_fields=("is_staff", "is_superuser"))
    request = RequestFactory().get("/django-admin/resources/resource/add/")
    request.user = actor
    model_admin = ResourceAdmin(Resource, admin.site)
    form_class = model_admin.get_form(request)
    form = form_class(
        data={
            "title": "后台发布验证资源",
            "slug": "admin-publish-check",
            "summary": "验证后台首次发布会自动记录发布时间。",
            "copyright_status": Resource.CopyrightStatus.SELF_MADE,
            "access_level": Resource.AccessLevel.PUBLIC,
            "status": Resource.Status.PUBLISHED,
        }
    )

    assert form.is_valid(), form.errors
    assert form.instance.published_at is not None


def test_mirror_rejects_embedded_account_credentials():
    resource = published_resource("credential-check", "入口凭据边界")

    with pytest.raises(ValidationError):
        ResourceMirror.objects.create(
            resource=resource,
            provider=ResourceMirror.Provider.OTHER,
            share_url="https://account:credential@pan.example.test/private",
        )


def test_resource_views_do_not_log_restricted_links_or_extraction_codes(client, caplog):
    resource = published_resource(
        "logging-check",
        RESTRICTED_TITLE,
        Resource.AccessLevel.ADVANCED,
    )
    active_mirror(resource)
    client.force_login(member(User.MembershipLevel.TRUSTED, "logs@example.com"))

    with caplog.at_level("INFO"):
        response = client.get(resource.get_absolute_url())

    assert response.status_code == 200
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert RESTRICTED_LINK not in logs
    assert RESTRICTED_CODE not in logs
    assert RESTRICTED_LINK not in str(resource.mirrors.get())
    assert RESTRICTED_CODE not in str(resource.mirrors.get())


def valid_csv():
    content = "\n".join(
        [
            "title,slug,summary,access_level,copyright_status,file_format,version,mirror_provider,share_url,extraction_code",
            "冷却水计算表,cooling-sheet,用于设计阶段复核冷却水参数。,L1,self_made,xlsx,v1.0,baidu,https://pan.example.test/s/cooling,AB12",
        ]
    )
    return SimpleUploadedFile("resources.csv", content.encode(), content_type="text/csv")


def test_csv_import_previews_before_atomic_confirmation_and_scrubs_duplicate_secrets():
    actor = member(User.MembershipLevel.OWNER, "owner@example.com")
    actor.is_staff = True
    actor.save(update_fields=("is_staff",))

    batch = preview_import(uploaded_file=valid_csv(), actor=actor)

    assert batch.state == ImportBatch.State.READY
    assert batch.row_count == 1
    assert Resource.objects.count() == 0
    row = batch.rows.get()
    assert row.state == ImportRow.State.VALID

    confirm_import(batch=batch, actor=actor)
    resource = Resource.objects.get(slug="cooling-sheet")
    row.refresh_from_db()

    assert resource.status == Resource.Status.PUBLISHED
    assert ResourceVersion.objects.get(resource=resource).version == "v1.0"
    mirror = ResourceMirror.objects.get(resource=resource)
    assert mirror.share_url == "https://pan.example.test/s/cooling"
    assert mirror.extraction_code == "AB12"
    assert row.state == ImportRow.State.IMPORTED
    assert row.normalized_data["share_url"] == "[已转入资源入口]"
    assert row.normalized_data["extraction_code"] == "[已转入资源入口]"


def test_import_error_cannot_create_partial_resources():
    actor = member(User.MembershipLevel.OWNER, "invalid-owner@example.com")
    actor.is_staff = True
    actor.save(update_fields=("is_staff",))
    content = "\n".join(
        [
            "title,slug,summary,access_level,copyright_status",
            "有效行,valid-row,说明,L0,self_made",
            "错误行,invalid-row,,L2,restricted",
        ]
    )
    upload = SimpleUploadedFile("invalid.csv", content.encode(), content_type="text/csv")

    batch = preview_import(uploaded_file=upload, actor=actor)

    assert batch.state == ImportBatch.State.INVALID
    assert batch.error_count == 1
    with pytest.raises(ValidationError):
        confirm_import(batch=batch, actor=actor)
    assert Resource.objects.count() == 0


def test_xlsx_preview_and_forbidden_credential_columns():
    actor = member(User.MembershipLevel.OWNER, "xlsx-owner@example.com")
    actor.is_staff = True
    actor.save(update_fields=("is_staff",))
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["资源名称", "网址标识", "简介", "访问等级", "版权状态"])
    sheet.append(["Excel 导入资源", "xlsx-resource", "Excel 预览验证", "L0", "自制"])
    stream = io.BytesIO()
    workbook.save(stream)
    workbook.close()
    xlsx = SimpleUploadedFile(
        "resources.xlsx",
        stream.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    batch = preview_import(uploaded_file=xlsx, actor=actor)
    assert batch.state == ImportBatch.State.READY
    assert batch.rows.get().normalized_data["slug"] == "xlsx-resource"

    forbidden = SimpleUploadedFile(
        "forbidden.csv",
        b"title,slug,summary,access_level,copyright_status,cloud_password\n"
        b"a,b,c,L0,self_made,secret",
        content_type="text/csv",
    )
    rejected = preview_import(uploaded_file=forbidden, actor=actor)
    assert rejected.state == ImportBatch.State.FAILED
    assert "密码" in rejected.error_message or "禁用字段" in rejected.error_message
    assert Resource.objects.count() == 0
