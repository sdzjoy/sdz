import hashlib
import json
from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from notifications.models import Event

from .models import (
    CandidateChange,
    CandidateReview,
    SourceEvidence,
    Standard,
    StandardStatusHistory,
)

DATE_FIELDS = {"published_on", "effective_on", "withdrawn_on"}
EDITABLE_FIELDS = {
    "title_cn",
    "title_en",
    "jurisdiction",
    "category",
    "nature",
    "status",
    "use_level",
    "country_region",
    "published_on",
    "effective_on",
    "withdrawn_on",
    "ics_code",
    "ccs_code",
    "summary",
}
NEW_STANDARD_FIELDS = EDITABLE_FIELDS | {"code", "slug"}


def _require_staff(actor):
    if actor is None or not actor.is_active or not actor.is_staff:
        raise PermissionDenied("只有管理员可以审核规范候选变化。")


def _coerce_field(name, value):
    if name not in DATE_FIELDS:
        return value
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValidationError({name: "日期必须使用 YYYY-MM-DD 格式。"}) from exc


def _validated_changes(proposed_data, *, allowed_fields):
    unknown = set(proposed_data) - allowed_fields
    if unknown:
        raise ValidationError("候选包含不允许自动写入的字段：" + "、".join(sorted(unknown)))
    return {name: _coerce_field(name, value) for name, value in proposed_data.items()}


def _create_evidence(candidate, standard, actor):
    differences = json.dumps(candidate.differences, ensure_ascii=False, sort_keys=True)
    content_hash = ""
    if candidate.snapshot_id:
        content_hash = candidate.snapshot.content_hash
    elif differences:
        content_hash = hashlib.sha256(differences.encode()).hexdigest()
    return SourceEvidence.objects.create(
        standard=standard,
        source_kind=SourceEvidence.SourceKind.OFFICIAL_PAGE,
        title=candidate.evidence_title,
        url=candidate.evidence_url,
        publisher=candidate.source.name,
        excerpt=differences[:2000],
        content_hash=content_hash,
        verified_by=actor,
        verified_at=timezone.now(),
    )


def _apply_to_existing(candidate, actor):
    changes = _validated_changes(candidate.proposed_data, allowed_fields=EDITABLE_FIELDS)
    standard = Standard.objects.select_for_update().get(pk=candidate.standard_id)
    previous_status = standard.status
    for name, value in changes.items():
        setattr(standard, name, value)
    evidence = _create_evidence(candidate, standard, actor)
    standard.full_clean()
    update_fields = set(changes) | {"updated_at"}
    standard.save(update_fields=tuple(sorted(update_fields)))

    history = None
    if standard.status != previous_status:
        history = StandardStatusHistory.objects.create(
            standard=standard,
            from_status=previous_status,
            to_status=standard.status,
            effective_on=standard.withdrawn_on or standard.effective_on or standard.published_on,
            evidence=evidence,
            changed_by=actor,
            note="由人工审核通过的低频检查候选产生。",
        )
    return standard, history


def _create_new_standard(candidate, actor):
    values = _validated_changes(candidate.proposed_data, allowed_fields=NEW_STANDARD_FIELDS)
    required = {"code", "slug", "title_cn", "category"}
    missing = required - {name for name, value in values.items() if value}
    if missing:
        raise ValidationError("新增标准缺少字段：" + "、".join(sorted(missing)))
    standard = Standard(**values)
    standard.full_clean()
    standard.save()
    _create_evidence(candidate, standard, actor)
    candidate.standard = standard
    candidate.save(update_fields=("standard",))
    return standard, None


@transaction.atomic
def approve_candidate(*, candidate, actor, note=""):
    _require_staff(actor)
    locked = (
        CandidateChange.objects.select_for_update()
        .select_related("source", "snapshot")
        .get(pk=candidate.pk)
    )
    if locked.state != CandidateChange.ReviewState.PENDING:
        raise ValidationError("该候选已经审核，不能重复处理。")
    if locked.change_type != CandidateChange.ChangeType.NEW_STANDARD and not locked.standard_id:
        raise ValidationError("该候选尚未关联正式标准。")

    if locked.change_type == CandidateChange.ChangeType.NEW_STANDARD:
        standard, history = _create_new_standard(locked, actor)
        event_type = Event.EventType.STANDARD_ADDED
    else:
        standard, history = _apply_to_existing(locked, actor)
        event_type = (
            Event.EventType.STANDARD_STATUS_CHANGED
            if history
            else Event.EventType.STANDARD_CHANGED
        )

    locked.state = CandidateChange.ReviewState.APPROVED
    locked.save(update_fields=("state",))
    review = CandidateReview.objects.create(
        candidate=locked,
        decision=CandidateReview.Decision.APPROVE,
        reviewer=actor,
        note=note.strip()[:1000],
        status_history=history,
    )
    Event.objects.create(
        event_type=event_type,
        title=f"{standard.code} {standard.title_cn}",
        payload={
            "standard_id": standard.pk,
            "standard_slug": standard.slug,
            "candidate_id": locked.pk,
            "status": standard.status,
        },
        dedupe_key=f"standard-candidate:{locked.pk}",
    )
    candidate.state = locked.state
    candidate.standard = standard
    return review


@transaction.atomic
def reject_candidate(*, candidate, actor, note=""):
    _require_staff(actor)
    locked = CandidateChange.objects.select_for_update().get(pk=candidate.pk)
    if locked.state != CandidateChange.ReviewState.PENDING:
        raise ValidationError("该候选已经审核，不能重复处理。")
    locked.state = CandidateChange.ReviewState.REJECTED
    locked.save(update_fields=("state",))
    review = CandidateReview.objects.create(
        candidate=locked,
        decision=CandidateReview.Decision.REJECT,
        reviewer=actor,
        note=note.strip()[:1000],
    )
    candidate.state = locked.state
    return review
