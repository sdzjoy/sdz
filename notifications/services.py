from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounts.models import User

from .models import (
    EmailDelivery,
    Event,
    ItemSubscription,
    NotificationPreference,
    TopicSubscription,
    UserNotification,
)


def emit_event(*, event_type, title, payload, dedupe_key, priority=Event.Priority.IMMEDIATE):
    event, _ = Event.objects.get_or_create(
        dedupe_key=dedupe_key,
        defaults={
            "event_type": event_type,
            "title": title,
            "payload": payload,
            "priority": priority,
        },
    )
    return event


def _category_for(event):
    if event.event_type.startswith("standard_"):
        return "immediate_standard"
    if event.event_type == Event.EventType.RESOURCE_IMPORTANT:
        return "immediate_resource"
    if event.event_type == Event.EventType.MEMBERSHIP_CHANGED:
        return "membership"
    if event.priority == Event.Priority.DIGEST:
        return "weekly_digest"
    return "security"


def _recipient_ids(event):
    payload = event.payload
    ids = set()
    if payload.get("user_id"):
        ids.add(int(payload["user_id"]))
    if payload.get("item_type") and payload.get("object_id"):
        ids.update(
            ItemSubscription.objects.filter(
                item_type=payload["item_type"], object_id=str(payload["object_id"])
            ).values_list("user_id", flat=True)
        )
    topic_ids = payload.get("topic_ids") or []
    if topic_ids:
        ids.update(
            TopicSubscription.objects.filter(taxonomy_id__in=topic_ids).values_list(
                "user_id", flat=True
            )
        )
    return ids


@transaction.atomic
def materialize_event(event):
    event = Event.objects.select_for_update().get(pk=event.pk)
    if event.materialized_at:
        return 0
    recipients = User.objects.filter(pk__in=_recipient_ids(event), is_active=True)
    category = _category_for(event)
    body = str(event.payload.get("summary", ""))[:2000]
    url = str(event.payload.get("url", ""))[:500]
    count = 0
    for user in recipients:
        notification, created = UserNotification.objects.get_or_create(
            user=user,
            event=event,
            defaults={"title": event.title, "body": body, "url": url},
        )
        count += int(created)
        if event.priority == Event.Priority.IMMEDIATE:
            EmailDelivery.objects.get_or_create(
                idempotency_key=f"event:{event.pk}:user:{user.pk}",
                defaults={
                    "user": user,
                    "event": event,
                    "delivery_type": EmailDelivery.DeliveryType.IMMEDIATE,
                    "category": category,
                    "subject": f"[少惰主] {event.title}",
                    "body": (
                        f"{event.title}\n\n{body}\n\n"
                        f"{settings.PUBLIC_SITE_ORIGIN.rstrip('/')}{url}"
                    ),
                },
            )
    event.materialized_at = timezone.now()
    event.save(update_fields=("materialized_at",))
    return count


def _preference_allows(delivery):
    preference, _ = NotificationPreference.objects.get_or_create(user=delivery.user)
    if not preference.email_enabled:
        return False
    return bool(getattr(preference, delivery.category, True))


def process_email_deliveries(*, max_attempts=3, limit=20):
    now = timezone.now()
    EmailDelivery.objects.filter(
        status=EmailDelivery.Status.SENDING,
        claimed_at__lt=now - timedelta(minutes=15),
    ).update(
        status=EmailDelivery.Status.RETRY,
        next_attempt_at=now,
        last_error="发送进程中断，已安全重新排队。",
    )
    delivery_ids = EmailDelivery.objects.filter(
        Q(status=EmailDelivery.Status.PENDING)
        | Q(status=EmailDelivery.Status.RETRY, next_attempt_at__lte=now)
    ).values_list("pk", flat=True)[:limit]
    results = {"sent": 0, "failed": 0, "skipped": 0}
    for delivery_id in delivery_ids:
        with transaction.atomic():
            delivery = (
                EmailDelivery.objects.select_for_update()
                .select_related("user")
                .get(pk=delivery_id)
            )
            if delivery.status not in {
                EmailDelivery.Status.PENDING,
                EmailDelivery.Status.RETRY,
            }:
                continue
            delivery.status = EmailDelivery.Status.SENDING
            delivery.claimed_at = timezone.now()
            delivery.attempts += 1
            delivery.save(update_fields=("status", "claimed_at", "attempts"))
        if not _preference_allows(delivery):
            delivery.status = EmailDelivery.Status.SKIPPED
            delivery.last_error = "用户已关闭该类邮件。"
            delivery.save(update_fields=("status", "last_error", "claimed_at"))
            results["skipped"] += 1
            continue
        try:
            send_mail(
                delivery.subject,
                delivery.body,
                settings.DEFAULT_FROM_EMAIL,
                [delivery.user.email],
                fail_silently=False,
            )
        except Exception as exc:  # SMTP providers expose different exception classes.
            delivery.last_error = f"{type(exc).__name__}: {exc}"[:500]
            if delivery.attempts >= max_attempts:
                delivery.status = EmailDelivery.Status.FAILED
                results["failed"] += 1
            else:
                delivery.status = EmailDelivery.Status.RETRY
                delivery.next_attempt_at = now + timedelta(minutes=5 * delivery.attempts)
            delivery.save(
                update_fields=(
                    "attempts",
                    "last_error",
                    "status",
                    "next_attempt_at",
                    "claimed_at",
                )
            )
            continue
        delivery.status = EmailDelivery.Status.SENT
        delivery.sent_at = timezone.now()
        delivery.last_error = ""
        delivery.save(
            update_fields=("attempts", "status", "sent_at", "last_error", "claimed_at")
        )
        results["sent"] += 1
    return results


def queue_weekly_digests(*, period_start=None):
    period_start = period_start or (timezone.localdate() - timedelta(days=7))
    since = timezone.make_aware(
        timezone.datetime.combine(period_start, timezone.datetime.min.time())
    )
    queued = 0
    users = User.objects.filter(is_active=True, notifications__created_at__gte=since).distinct()
    for user in users:
        preference, _ = NotificationPreference.objects.get_or_create(user=user)
        if not preference.email_enabled or not preference.weekly_digest:
            continue
        items = list(user.notifications.filter(created_at__gte=since).order_by("created_at")[:50])
        if not items:
            continue
        body = "本周更新\n\n" + "\n".join(f"- {item.title}" for item in items)
        _, created = EmailDelivery.objects.get_or_create(
            idempotency_key=f"weekly:{period_start.isoformat()}:user:{user.pk}",
            defaults={
                "user": user,
                "delivery_type": EmailDelivery.DeliveryType.WEEKLY,
                "category": "weekly_digest",
                "subject": f"[少惰主] {period_start.isoformat()} 每周更新",
                "body": body,
            },
        )
        queued += int(created)
    return queued
