from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Standard, StandardStatusHistory, TaxonomyTerm


def _require_staff(actor):
    if actor is None or not actor.is_active or not actor.is_staff:
        raise PermissionDenied("只有管理员可以核验或变更标准状态。")


@transaction.atomic
def mark_standard_verified(*, standard, evidence, actor):
    _require_staff(actor)
    locked = Standard.objects.select_for_update().get(pk=standard.pk)
    if evidence.standard_id != locked.pk:
        raise ValidationError("来源证据不属于该标准。")
    now = timezone.now()
    evidence.verified_at = now
    evidence.verified_by = actor
    evidence.save(update_fields=("verified_at", "verified_by"))
    locked.verification_state = Standard.VerificationState.VERIFIED
    locked.last_verified_at = now
    locked.verified_by = actor
    locked.full_clean()
    locked.save(
        update_fields=("verification_state", "last_verified_at", "verified_by", "updated_at")
    )
    standard.verification_state = locked.verification_state
    standard.last_verified_at = now
    standard.verified_by = actor
    return locked


@transaction.atomic
def change_standard_status(*, standard, to_status, evidence, actor, note=""):
    _require_staff(actor)
    if to_status not in Standard.Status.values:
        raise ValidationError("未知标准状态。")
    locked = Standard.objects.select_for_update().get(pk=standard.pk)
    if evidence.standard_id != locked.pk:
        raise ValidationError("状态变更证据不属于该标准。")
    from_status = locked.status
    if from_status == to_status:
        return None
    locked.status = to_status
    locked.full_clean()
    locked.save(update_fields=("status", "updated_at"))
    history = StandardStatusHistory.objects.create(
        standard=locked,
        from_status=from_status,
        to_status=to_status,
        effective_on=locked.withdrawn_on or locked.effective_on or locked.published_on,
        evidence=evidence,
        changed_by=actor,
        note=note.strip()[:500],
    )
    standard.status = to_status
    return history


def build_coverage_matrix():
    systems = TaxonomyTerm.objects.filter(kind=TaxonomyTerm.Kind.SYSTEM)
    stages = TaxonomyTerm.objects.filter(kind=TaxonomyTerm.Kind.DESIGN_STAGE)
    eligible = Standard.objects.filter(
        jurisdiction=Standard.Jurisdiction.DOMESTIC,
        status__in=(Standard.Status.CURRENT, Standard.Status.UPCOMING),
        verification_state=Standard.VerificationState.VERIFIED,
    )
    rows = []
    for system in systems:
        cells = []
        for stage in stages:
            standards = eligible.filter(taxonomies=system).filter(taxonomies=stage).distinct()
            cells.append(
                {
                    "stage": stage,
                    "count": standards.count(),
                    "standards": list(standards.order_by("code")[:10]),
                }
            )
        rows.append(
            {
                "system": system,
                "cells": cells,
                "is_gap": not any(cell["count"] for cell in cells),
            }
        )
    return {"stages": list(stages), "rows": rows}
