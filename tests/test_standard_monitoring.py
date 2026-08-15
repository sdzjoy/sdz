import json
from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from accounts.models import User
from notifications.models import Event
from standards.models import (
    CandidateChange,
    CandidateReview,
    CheckBatch,
    MonitoringSource,
    Standard,
    StandardStatusHistory,
)
from standards.monitoring import HTTPResult, candidate_fingerprint, run_source_check
from standards.reviews import approve_candidate, reject_candidate

pytestmark = pytest.mark.django_db


def staff_user():
    return User.objects.create_user(email="monitor@example.com", is_staff=True)


def standard_record():
    return Standard.objects.create(
        code="GB MONITOR-1",
        slug="monitor-standard",
        title_cn="规范变更助手测试标准",
        category=Standard.Category.NATIONAL,
        status=Standard.Status.CURRENT,
        published_on=date(2025, 1, 1),
        effective_on=date(2025, 2, 1),
    )


def automated_source():
    return MonitoringSource.objects.create(
        name="示例官方月度增量源",
        slug="official-monthly-fixture",
        source_url="https://standards.example.gov.test/monthly.json",
        feed_format=MonitoringSource.FeedFormat.SDZJOY_JSON,
        automated_access_allowed=True,
        access_reviewed_at=timezone.now(),
    )


def fixture_payload(standard):
    return {
        "items": [
            {
                "external_key": "notice-2026-001",
                "standard_slug": standard.slug,
                "change_type": CandidateChange.ChangeType.STATUS,
                "proposed_data": {
                    "status": Standard.Status.WITHDRAWN,
                    "withdrawn_on": "2026-09-01",
                },
                "differences": {"status": ["current", "withdrawn"]},
                "evidence": {
                    "title": "关于标准废止的官方公告",
                    "url": "https://standards.example.gov.test/notices/2026-001",
                },
            }
        ]
    }


def candidate_for(standard):
    source = MonitoringSource.objects.create(
        name="人工核验来源",
        slug="manual-review-source",
        source_url="https://standards.example.gov.test/notices/",
    )
    proposed_data = {
        "status": Standard.Status.WITHDRAWN,
        "withdrawn_on": "2026-09-01",
    }
    return CandidateChange.objects.create(
        source=source,
        standard=standard,
        external_key="manual-notice-1",
        fingerprint=candidate_fingerprint(
            external_key="manual-notice-1",
            change_type=CandidateChange.ChangeType.STATUS,
            proposed_data=proposed_data,
        ),
        change_type=CandidateChange.ChangeType.STATUS,
        proposed_data=proposed_data,
        differences={"status": ["current", "withdrawn"]},
        evidence_title="官方废止公告",
        evidence_url="https://standards.example.gov.test/notices/manual-1",
    )


def test_no_automated_source_is_enabled_by_default():
    assert MonitoringSource.objects.filter(enabled=True).count() == 0


def test_repeated_fixture_run_is_idempotent_and_uses_no_third_party_network():
    standard = standard_record()
    source = automated_source()
    body = json.dumps(fixture_payload(standard), ensure_ascii=False).encode()

    def local_fetcher(unused_source):
        return HTTPResult(
            status=200,
            headers={"ETag": '"fixture-v1"'},
            body=body,
        )

    first = run_source_check(source=source, fetcher=local_fetcher)
    second = run_source_check(source=source, fetcher=local_fetcher)

    assert first.status == CheckBatch.Status.COMPLETED
    assert first.candidate_count == 1
    assert second.status == CheckBatch.Status.NO_CHANGE
    assert second.candidate_count == 0
    assert CandidateChange.objects.count() == 1
    assert Standard.objects.get(pk=standard.pk).status == Standard.Status.CURRENT


def test_rate_limit_stops_batch_and_records_backoff():
    source = automated_source()

    batch = run_source_check(
        source=source,
        fetcher=lambda unused_source: HTTPResult(
            status=429,
            headers={"Retry-After": "7200"},
            body=b"",
        ),
    )
    source.refresh_from_db()

    assert batch.status == CheckBatch.Status.RATE_LIMITED
    assert source.next_allowed_at is not None
    assert CandidateChange.objects.count() == 0


def test_source_error_records_failure_without_changing_standards():
    standard = standard_record()
    source = automated_source()

    batch = run_source_check(
        source=source,
        fetcher=lambda unused_source: HTTPResult(status=503, headers={}, body=b""),
    )
    standard.refresh_from_db()

    assert batch.status == CheckBatch.Status.FAILED
    assert "HTTP 503" in batch.message
    assert standard.status == Standard.Status.CURRENT
    assert not StandardStatusHistory.objects.exists()


def test_second_running_batch_for_same_source_is_blocked():
    source = automated_source()
    CheckBatch.objects.create(source=source, trigger=CheckBatch.Trigger.MANUAL)

    with pytest.raises(ValidationError):
        run_source_check(
            source=source,
            fetcher=lambda unused_source: HTTPResult(status=304, headers={}, body=b""),
        )


def test_rejecting_candidate_does_not_change_formal_record():
    standard = standard_record()
    candidate = candidate_for(standard)

    review = reject_candidate(candidate=candidate, actor=staff_user(), note="公告对象不匹配。")
    standard.refresh_from_db()
    candidate.refresh_from_db()

    assert review.decision == CandidateReview.Decision.REJECT
    assert candidate.state == CandidateChange.ReviewState.REJECTED
    assert standard.status == Standard.Status.CURRENT
    assert not StandardStatusHistory.objects.exists()
    assert not Event.objects.exists()


def test_approving_status_candidate_creates_evidence_history_and_event():
    standard = standard_record()
    candidate = candidate_for(standard)
    actor = staff_user()

    review = approve_candidate(candidate=candidate, actor=actor, note="已对照公告人工确认。")
    standard.refresh_from_db()
    candidate.refresh_from_db()

    assert candidate.state == CandidateChange.ReviewState.APPROVED
    assert standard.status == Standard.Status.WITHDRAWN
    assert standard.withdrawn_on == date(2026, 9, 1)
    assert standard.evidence.filter(verified_by=actor).exists()
    history = StandardStatusHistory.objects.get(standard=standard)
    assert history.from_status == Standard.Status.CURRENT
    assert history.to_status == Standard.Status.WITHDRAWN
    assert review.status_history == history
    event = Event.objects.get()
    assert event.event_type == Event.EventType.STANDARD_STATUS_CHANGED
    assert event.payload["standard_id"] == standard.pk
