"""
Tests für den deterministischen Eligibility-Filter (Layer 2, §4.1).
Kein LLM, keine DB — reine Python-Logik.
"""

from datetime import datetime, timezone

import pytest

from careapp.domain.eligibility import (
    ClaimVersionSnapshot,
    EligibilityResult,
    EvidenceSnapshot,
    RequestContext,
    ScopeAssignmentSnapshot,
    is_answer_eligible,
)

T = datetime(2025, 6, 1, tzinfo=timezone.utc)
BEFORE = datetime(2024, 1, 1, tzinfo=timezone.utc)
AFTER = datetime(2026, 1, 1, tzinfo=timezone.utc)

BASE_CV = ClaimVersionSnapshot(
    id="cv-1",
    status="published",
    region_binding="region_independent",
    effective_from=BEFORE,
    effective_to=None,
    published_at=BEFORE,
    unpublished_at=None,
    tenant_visibility=None,
    conflicting=False,
)

BASE_SCOPES = [
    ScopeAssignmentSnapshot(dimension="region", value="DE_FEDERAL", applies=True),
    ScopeAssignmentSnapshot(dimension="target_group", value="relative", applies=True),
    ScopeAssignmentSnapshot(dimension="topic", value="stationaere_pflege", applies=True),
]

BASE_EVIDENCES = [
    EvidenceSnapshot(role="carrying", passage_exists=True),
]

BASE_CTX = RequestContext(
    requested_at=T,
    region_id="NW-KREIS-NEUSS",
    target_group_codes=("relative",),
    tenant_id=None,
    topic_scope="stationaere_pflege",
    locale="de",
)


def test_happy_path_eligible():
    result = is_answer_eligible(BASE_CV, BASE_SCOPES, BASE_EVIDENCES, BASE_CTX)
    assert result.is_eligible


# ---- Gate 1: status ----

def test_gate1_draft_not_eligible():
    cv = BASE_CV.__class__(**{**BASE_CV.__dict__, "status": "draft"})
    result = is_answer_eligible(cv, BASE_SCOPES, BASE_EVIDENCES, BASE_CTX)
    assert result.result == EligibilityResult.NOT_ELIGIBLE
    assert result.failed_gate == 1


def test_gate1_in_review_not_eligible():
    cv = BASE_CV.__class__(**{**BASE_CV.__dict__, "status": "in_review"})
    result = is_answer_eligible(cv, BASE_SCOPES, BASE_EVIDENCES, BASE_CTX)
    assert result.failed_gate == 1


# ---- Gate 2: published_at / effective_from ----

def test_gate2_missing_published_at():
    cv = BASE_CV.__class__(**{**BASE_CV.__dict__, "published_at": None})
    result = is_answer_eligible(cv, BASE_SCOPES, BASE_EVIDENCES, BASE_CTX)
    assert result.failed_gate == 2


def test_gate2_missing_effective_from():
    cv = BASE_CV.__class__(**{**BASE_CV.__dict__, "effective_from": None})
    result = is_answer_eligible(cv, BASE_SCOPES, BASE_EVIDENCES, BASE_CTX)
    assert result.failed_gate == 2


# ---- Gate 3: Zeitfenster ----

def test_gate3_requested_before_effective_from():
    cv = BASE_CV.__class__(**{**BASE_CV.__dict__, "effective_from": AFTER})
    result = is_answer_eligible(cv, BASE_SCOPES, BASE_EVIDENCES, BASE_CTX)
    assert result.failed_gate == 3


def test_gate3_requested_after_effective_to():
    cv = BASE_CV.__class__(**{**BASE_CV.__dict__, "effective_to": BEFORE})
    result = is_answer_eligible(cv, BASE_SCOPES, BASE_EVIDENCES, BASE_CTX)
    assert result.failed_gate == 3


def test_gate3_on_effective_to_boundary_not_eligible():
    cv = BASE_CV.__class__(**{**BASE_CV.__dict__, "effective_to": T})
    result = is_answer_eligible(cv, BASE_SCOPES, BASE_EVIDENCES, BASE_CTX)
    assert result.failed_gate == 3


# ---- Gate 4: unpublished_at ----

def test_gate4_unpublished():
    cv = BASE_CV.__class__(**{**BASE_CV.__dict__, "unpublished_at": BEFORE})
    result = is_answer_eligible(cv, BASE_SCOPES, BASE_EVIDENCES, BASE_CTX)
    assert result.failed_gate == 4


# ---- Gate 5: Region (D6) ----

def test_gate5_region_specific_without_region_id():
    cv = BASE_CV.__class__(**{**BASE_CV.__dict__, "region_binding": "region_specific"})
    scopes = [s for s in BASE_SCOPES if s.dimension != "region"] + [
        ScopeAssignmentSnapshot(dimension="region", value="NW-KREIS-NEUSS", applies=True)
    ]
    ctx = BASE_CTX.__class__(**{**BASE_CTX.__dict__, "region_id": None})
    result = is_answer_eligible(cv, scopes, BASE_EVIDENCES, ctx)
    assert result.failed_gate == 5


def test_gate5_region_specific_wrong_region():
    cv = BASE_CV.__class__(**{**BASE_CV.__dict__, "region_binding": "region_specific"})
    scopes = [s for s in BASE_SCOPES if s.dimension != "region"] + [
        ScopeAssignmentSnapshot(dimension="region", value="BY-MUENCHEN", applies=True)
    ]
    result = is_answer_eligible(cv, scopes, BASE_EVIDENCES, BASE_CTX)
    assert result.failed_gate == 5


def test_gate5_region_independent_passes_without_region_id():
    ctx = BASE_CTX.__class__(**{**BASE_CTX.__dict__, "region_id": None})
    result = is_answer_eligible(BASE_CV, BASE_SCOPES, BASE_EVIDENCES, ctx)
    assert result.is_eligible


# ---- Gate 6: Zielgruppe ----

def test_gate6_wrong_target_group():
    ctx = BASE_CTX.__class__(**{**BASE_CTX.__dict__, "target_group_codes": ("professional",)})
    result = is_answer_eligible(BASE_CV, BASE_SCOPES, BASE_EVIDENCES, ctx)
    assert result.failed_gate == 6


# ---- Gate 7: Themenbereich ----

def test_gate7_wrong_topic():
    ctx = BASE_CTX.__class__(**{**BASE_CTX.__dict__, "topic_scope": "widerspruch_pflegegrad"})
    result = is_answer_eligible(BASE_CV, BASE_SCOPES, BASE_EVIDENCES, ctx)
    assert result.failed_gate == 7


# ---- Gate 8: Mandant ----

def test_gate8_tenant_restricted_unknown_tenant():
    cv = BASE_CV.__class__(**{**BASE_CV.__dict__, "tenant_visibility": "org-xyz"})
    ctx = BASE_CTX.__class__(**{**BASE_CTX.__dict__, "tenant_id": None})
    result = is_answer_eligible(cv, BASE_SCOPES, BASE_EVIDENCES, ctx)
    assert result.failed_gate == 8


def test_gate8_tenant_mismatch():
    cv = BASE_CV.__class__(**{**BASE_CV.__dict__, "tenant_visibility": "org-xyz"})
    ctx = BASE_CTX.__class__(**{**BASE_CTX.__dict__, "tenant_id": "org-abc"})
    result = is_answer_eligible(cv, BASE_SCOPES, BASE_EVIDENCES, ctx)
    assert result.failed_gate == 8


def test_gate8_correct_tenant_passes():
    cv = BASE_CV.__class__(**{**BASE_CV.__dict__, "tenant_visibility": "org-xyz"})
    ctx = BASE_CTX.__class__(**{**BASE_CTX.__dict__, "tenant_id": "org-xyz"})
    result = is_answer_eligible(cv, BASE_SCOPES, BASE_EVIDENCES, ctx)
    assert result.is_eligible


# ---- Gate 9: carrying evidence ----

def test_gate9_no_carrying_evidence():
    evidences = [EvidenceSnapshot(role="supporting", passage_exists=True)]
    result = is_answer_eligible(BASE_CV, BASE_SCOPES, evidences, BASE_CTX)
    assert result.failed_gate == 9


def test_gate9_carrying_but_passage_missing():
    evidences = [EvidenceSnapshot(role="carrying", passage_exists=False)]
    result = is_answer_eligible(BASE_CV, BASE_SCOPES, evidences, BASE_CTX)
    assert result.failed_gate == 9


def test_gate9_no_evidence_at_all():
    result = is_answer_eligible(BASE_CV, BASE_SCOPES, [], BASE_CTX)
    assert result.failed_gate == 9


# ---- Gate 10: conflicting / withdrawn / superseded ----

def test_gate10_conflicting():
    cv = BASE_CV.__class__(**{**BASE_CV.__dict__, "conflicting": True})
    result = is_answer_eligible(cv, BASE_SCOPES, BASE_EVIDENCES, BASE_CTX)
    assert result.failed_gate == 10


def test_gate10_withdrawn():
    cv = BASE_CV.__class__(**{**BASE_CV.__dict__, "status": "withdrawn"})
    # Status withdrawn aber published_at gesetzt — Gate 10 sollte aber nicht
    # erreicht werden da Gate 1 bereits "published" erwartet.
    # Test für Gate 1 reicht hier.
    result = is_answer_eligible(cv, BASE_SCOPES, BASE_EVIDENCES, BASE_CTX)
    assert result.failed_gate == 1
