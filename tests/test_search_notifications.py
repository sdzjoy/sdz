from datetime import date
from unittest.mock import patch

import pytest
from django.core import mail
from django.db import DatabaseError
from django.utils import timezone

from accounts.models import User
from notifications.models import (
    EmailDelivery,
    Event,
    ItemSubscription,
    NotificationPreference,
    UserNotification,
)
from notifications.services import (
    emit_event,
    materialize_event,
    process_email_deliveries,
    queue_weekly_digests,
)
from resources.models import Resource
from searchapp.models import SearchDocument
from standards.models import Standard

pytestmark = pytest.mark.django_db


def user(level="L1", email="member@example.com"):
    return User.objects.create_user(email=email, membership_level=level, is_active=True)


def standard():
    return Standard.objects.create(
        code="GB 50019-2015",
        slug="gb-50019-2015-search",
        title_cn="工业建筑供暖通风与空气调节设计规范",
        category=Standard.Category.NATIONAL,
        status=Standard.Status.CURRENT,
        effective_on=date(2016, 2, 1),
    )


def resource(level, title):
    return Resource.objects.create(
        title=title,
        slug=title.lower().replace(" ", "-"),
        summary=f"{title} 摘要",
        access_level=level,
        status=Resource.Status.PUBLISHED,
        published_at=timezone.now(),
    )


def test_search_groups_results_and_filters_before_rendering(client):
    record = standard()
    public = resource(Resource.AccessLevel.PUBLIC, "Public Airflow Tool")
    restricted = resource(Resource.AccessLevel.ADVANCED, "Secret Airflow Library")

    assert SearchDocument.objects.filter(object_id=record.pk, kind="standard").exists()
    response = client.get("/search/?q=Airflow")
    body = response.content.decode()
    assert public.title in body
    assert restricted.title not in body
    assert response["Cache-Control"] == "private, no-store"

    advanced = user("L2", "advanced@example.com")
    client.force_login(advanced)
    body = client.get("/search/?q=Airflow").content.decode()
    assert public.title in body
    assert restricted.title in body

    advanced.membership_level = "L1"
    advanced.save(update_fields=("membership_level",))
    assert restricted.title not in client.get("/search/?q=Airflow").content.decode()


def test_search_dependency_failure_degrades_without_breaking_browse(client):
    with patch("searchapp.views.search_documents", side_effect=DatabaseError("offline")):
        response = client.get("/search/?q=GB")
    assert response.status_code == 200
    assert "搜索暂时不可用" in response.content.decode()
    assert client.get("/standards/").status_code == 200


def test_event_delivery_is_idempotent_and_unsubscribe_is_immediate():
    member = user()
    item = standard()
    ItemSubscription.objects.create(user=member, item_type="standard", object_id=item.pk)
    event = emit_event(
        event_type=Event.EventType.STANDARD_STATUS_CHANGED,
        title="规范状态变化",
        payload={
            "item_type": "standard",
            "object_id": item.pk,
            "summary": "现行状态已更新。",
            "url": item.get_absolute_url(),
        },
        dedupe_key="test-standard-change",
    )

    assert materialize_event(event) == 1
    assert materialize_event(event) == 0
    assert UserNotification.objects.filter(user=member, event=event).count() == 1
    assert EmailDelivery.objects.filter(user=member, event=event).count() == 1

    process_email_deliveries()
    process_email_deliveries()
    assert len(mail.outbox) == 1

    second = emit_event(
        event_type=Event.EventType.STANDARD_CHANGED,
        title="第二次规范变化",
        payload={"item_type": "standard", "object_id": item.pk},
        dedupe_key="test-standard-change-2",
    )
    materialize_event(second)
    preference, _ = NotificationPreference.objects.get_or_create(user=member)
    preference.immediate_standard = False
    preference.save()
    result = process_email_deliveries()
    assert result["skipped"] == 1
    assert len(mail.outbox) == 1


def test_mail_failure_is_limited_and_does_not_rollback_event():
    member = user()
    item = standard()
    ItemSubscription.objects.create(user=member, item_type="standard", object_id=item.pk)
    event = emit_event(
        event_type=Event.EventType.STANDARD_CHANGED,
        title="邮件失败仍保留",
        payload={"item_type": "standard", "object_id": item.pk},
        dedupe_key="mail-failure-event",
    )
    materialize_event(event)
    with patch("notifications.services.send_mail", side_effect=OSError("smtp unavailable")):
        result = process_email_deliveries(max_attempts=1)
    assert result["failed"] == 1
    assert Event.objects.filter(pk=event.pk).exists()
    assert EmailDelivery.objects.get(event=event).status == EmailDelivery.Status.FAILED


def test_weekly_digest_queue_is_idempotent():
    member = user()
    item = standard()
    ItemSubscription.objects.create(user=member, item_type="standard", object_id=item.pk)
    event = emit_event(
        event_type=Event.EventType.CONTENT_PUBLISHED,
        title="本周新内容",
        payload={"item_type": "standard", "object_id": item.pk},
        dedupe_key="weekly-content-event",
        priority=Event.Priority.DIGEST,
    )
    materialize_event(event)

    assert queue_weekly_digests() == 1
    assert queue_weekly_digests() == 0
    assert EmailDelivery.objects.filter(delivery_type="weekly", user=member).count() == 1


def test_low_level_user_cannot_save_restricted_resource(client):
    member = user()
    restricted = resource(Resource.AccessLevel.ADVANCED, "Private CFD Pack")
    client.force_login(member)
    response = client.post(
        "/account/saved/favorite/toggle/",
        {"item_type": "resource", "object_id": restricted.pk},
    )
    assert response.status_code == 403
    assert not member.favorites.exists()
