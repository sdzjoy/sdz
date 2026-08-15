from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from accounts.models import User
from standards.models import (
    Manual,
    ReferenceBook,
    SourceEvidence,
    Standard,
    StandardRelation,
    TaxonomyTerm,
)
from standards.services import build_coverage_matrix, mark_standard_verified

pytestmark = pytest.mark.django_db


def standard_record(code, slug, **overrides):
    values = {
        "code": code,
        "slug": slug,
        "title_cn": f"{code} 测试标准",
        "jurisdiction": Standard.Jurisdiction.DOMESTIC,
        "category": Standard.Category.NATIONAL,
        "status": Standard.Status.CURRENT,
        "effective_on": date(2025, 1, 1),
    }
    values.update(overrides)
    return Standard.objects.create(**values)


def staff_user():
    return User.objects.create_user(
        email="reviewer@example.com",
        is_staff=True,
    )


def evidence_for(standard):
    return SourceEvidence.objects.create(
        standard=standard,
        source_kind=SourceEvidence.SourceKind.OFFICIAL_PAGE,
        title="官方标准信息页",
        url=f"https://example.gov.test/standards/{standard.slug}",
        is_primary=True,
    )


def test_status_and_lifecycle_dates_are_validated():
    standard = Standard(
        code="GB TEST-1",
        slug="invalid-lifecycle",
        title_cn="日期组合测试",
        category=Standard.Category.NATIONAL,
        status=Standard.Status.CURRENT,
        published_on=date(2025, 2, 1),
        effective_on=date(2025, 1, 1),
    )

    with pytest.raises(ValidationError) as error:
        standard.full_clean()

    assert "effective_on" in error.value.message_dict

    standard.published_on = date(2025, 1, 1)
    standard.effective_on = None
    with pytest.raises(ValidationError) as error:
        standard.full_clean()
    assert "effective_on" in error.value.message_dict


def test_replacement_relation_blocks_self_reference_and_cycles():
    first = standard_record("GB TEST-A", "test-a")
    second = standard_record("GB TEST-B", "test-b")
    third = standard_record("GB TEST-C", "test-c")

    with pytest.raises(ValidationError):
        StandardRelation.objects.create(
            source=first,
            target=first,
            relation_type=StandardRelation.RelationType.SUPERSEDES,
        )

    StandardRelation.objects.create(
        source=first,
        target=second,
        relation_type=StandardRelation.RelationType.SUPERSEDES,
    )
    StandardRelation.objects.create(
        source=second,
        target=third,
        relation_type=StandardRelation.RelationType.SUPERSEDES,
    )
    with pytest.raises(ValidationError):
        StandardRelation.objects.create(
            source=third,
            target=first,
            relation_type=StandardRelation.RelationType.SUPERSEDES,
        )


def test_standard_cannot_be_verified_without_source_evidence():
    standard = standard_record("GB TEST-2", "missing-evidence")
    actor = staff_user()
    standard.verification_state = Standard.VerificationState.VERIFIED
    standard.last_verified_at = timezone.now()
    standard.verified_by = actor

    with pytest.raises(ValidationError) as error:
        standard.full_clean()

    assert "verification_state" in error.value.message_dict


def test_verification_service_records_actor_and_evidence():
    standard = standard_record("GB TEST-3", "verified-standard")
    actor = staff_user()
    evidence = evidence_for(standard)

    mark_standard_verified(standard=standard, evidence=evidence, actor=actor)
    standard.refresh_from_db()
    evidence.refresh_from_db()

    assert standard.verification_state == Standard.VerificationState.VERIFIED
    assert standard.verified_by == actor
    assert evidence.verified_by == actor
    assert evidence.verified_at is not None


def test_public_filter_and_detail_distinguish_domestic_and_foreign(client):
    domestic = standard_record("GB TEST-4", "domestic-basis", title_cn="国内设计依据测试")
    foreign = standard_record(
        "ASHRAE TEST-1",
        "foreign-reference",
        title_cn="国外技术参考测试",
        jurisdiction=Standard.Jurisdiction.FOREIGN,
        category=Standard.Category.FOREIGN,
        country_region="美国",
    )

    filtered = client.get("/standards/?jurisdiction=foreign").content.decode()
    detail = client.get(foreign.get_absolute_url()).content.decode()

    assert foreign.title_cn in filtered
    assert domestic.title_cn not in filtered
    assert "国外技术参考" in detail
    assert "不能直接替代中国项目" in detail


def test_coverage_matrix_exposes_gaps_and_only_counts_eligible_domestic_records():
    system = TaxonomyTerm.objects.get(kind=TaxonomyTerm.Kind.SYSTEM, slug="air_system")
    stage = TaxonomyTerm.objects.get(
        kind=TaxonomyTerm.Kind.DESIGN_STAGE,
        slug="detailed_design",
    )
    actor = staff_user()
    eligible = standard_record("GB TEST-5", "matrix-eligible")
    eligible.taxonomies.add(system, stage)
    mark_standard_verified(
        standard=eligible,
        evidence=evidence_for(eligible),
        actor=actor,
    )
    foreign = standard_record(
        "ASHRAE TEST-2",
        "matrix-foreign",
        jurisdiction=Standard.Jurisdiction.FOREIGN,
        category=Standard.Category.FOREIGN,
    )
    foreign.taxonomies.add(system, stage)
    mark_standard_verified(
        standard=foreign,
        evidence=evidence_for(foreign),
        actor=actor,
    )

    matrix = build_coverage_matrix()
    row = next(item for item in matrix["rows"] if item["system"] == system)
    cell = next(item for item in row["cells"] if item["stage"] == stage)

    assert cell["count"] == 1
    assert cell["standards"] == [eligible]
    assert any(item["is_gap"] for item in matrix["rows"])


def test_manuals_and_reference_books_have_independent_catalogs(client):
    manual = Manual.objects.create(
        title="数据中心冷却技术手册",
        slug="cooling-manual",
        authors="测试编委会",
    )
    book = ReferenceBook.objects.create(
        title="暖通设计参考书",
        slug="hvac-reference-book",
        authors="测试作者",
    )

    listing = client.get("/standards/library/").content.decode()

    assert manual.title in listing
    assert book.title in listing
    assert client.get(manual.get_absolute_url()).status_code == 200
    assert client.get(book.get_absolute_url()).status_code == 200
