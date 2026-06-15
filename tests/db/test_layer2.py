"""
Integrationstests für Layer 2 (Evidence Builder, Coverage, Validator).
Laufen gegen echte Supabase-Instanz (kein Mock, kein Docker).

Jeder Test bekommt eine saubere DB (TRUNCATE + COMMIT am Anfang und Ende).
Alle Testdaten verwenden zufällige UUIDs, um Konflikte mit Parallelläufen zu vermeiden.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from careapp.db.models.claim import (
    ActorRole,
    Approval,
    Claim,
    ClaimEvidence,
    ClaimRelation,
    ClaimRelationKind,
    ClaimVersion,
    ClaimVersionStatus,
    EvidenceRole,
    RegionBinding,
    ScopeAssignment,
    ScopeDimension,
    StructuredValue,
    StructuredValueKind,
)
from careapp.db.models.source import (
    SourceDocument,
    SourcePassage,
    SourceType,
    SourceVersion,
)
from careapp.domain.coverage import CoverageGrade, compute_coverage
from careapp.domain.eligibility import RequestContext
from careapp.domain.evidence_builder import (
    StructuredValueRecord,
    build_evidence_package,
)
from careapp.domain.validator import FactualStatement, validate_statements

# ------------------------------------------------------------------ #
# Zeitkonstanten                                                       #
# ------------------------------------------------------------------ #

T_PAST = datetime(2024, 1, 1, tzinfo=timezone.utc)
T_PRESENT = datetime(2025, 6, 1, tzinfo=timezone.utc)   # Standard ctx.requested_at
T_EXPIRED = datetime(2025, 1, 1, tzinfo=timezone.utc)   # Ablaufdatum vor T_PRESENT
T_LATER = datetime(2025, 8, 1, tzinfo=timezone.utc)     # Für TOCTOU-Test

_TRUNCATE_ALL = text(
    "TRUNCATE TABLE pathway_branch, pathway_step, decision_node, approval, "
    "scope_assignment, structured_value, claim_evidence, claim_version, claim, "
    "life_situation_pathway, life_situation, source_passage, source_version, "
    "source_document CASCADE;"
)

BASE_CTX = RequestContext(
    requested_at=T_PRESENT,
    region_id="NW-KREIS-NEUSS",
    target_group_codes=("relative",),
    tenant_id=None,
    topic_scope="stationaere_pflege",
    locale="de",
)


# ------------------------------------------------------------------ #
# Fixtures                                                             #
# ------------------------------------------------------------------ #


@pytest.fixture
async def db_clean(session):
    """Leer räumen vor und nach jedem Test."""
    await session.execute(_TRUNCATE_ALL)
    await session.commit()
    yield session
    await session.execute(_TRUNCATE_ALL)
    await session.commit()


# ------------------------------------------------------------------ #
# Hilfsklasse: synthetische Testdaten mit zufälligen UUIDs            #
# ------------------------------------------------------------------ #


class _Builder:
    """Erzeugt synthetische DB-Objekte mit frischen UUIDs pro Instanz."""

    def __init__(self):
        self.source_doc_id = uuid.uuid4()
        self.source_version_id = uuid.uuid4()
        self.passage_id = uuid.uuid4()

    def source_objects(self) -> list:
        return [
            SourceDocument(
                id=self.source_doc_id,
                type=SourceType.law,
                publisher="SYNTHETISCH",
                canonical_ref=f"SYN-{self.source_doc_id}",
                created_at=T_PAST,
            ),
            SourceVersion(
                id=self.source_version_id,
                source_document_id=self.source_doc_id,
                content_hash="a" * 64,
                edition_label="Test",
                imported_at=T_PAST,
                object_store_uri="s3://test/test.pdf",
            ),
            SourcePassage(
                id=self.passage_id,
                source_version_id=self.source_version_id,
                anchor={"section": "§1 (SYNTHETISCH)"},
                text="SYNTHETISCH: Testtext.",
            ),
        ]

    def claim(
        self,
        topic_scope: str = "stationaere_pflege",
        region_binding: RegionBinding = RegionBinding.region_independent,
    ) -> Claim:
        return Claim(
            id=uuid.uuid4(),
            topic_scope=topic_scope,
            region_binding=region_binding,
            created_at=T_PAST,
        )

    def published_cv(
        self,
        claim_id: uuid.UUID,
        *,
        effective_to: datetime | None = None,
        conflicting: bool = False,
        status: ClaimVersionStatus = ClaimVersionStatus.published,
    ) -> ClaimVersion:
        return ClaimVersion(
            id=uuid.uuid4(),
            claim_id=claim_id,
            statement_text="SYNTHETISCH: Testaussage.",
            status=status,
            effective_from=T_PAST,
            effective_to=effective_to,
            published_at=T_PAST,
            unpublished_at=None,
            tenant_visibility=None,
            conflicting=conflicting,
        )

    def carrying_evidence(self, cv_id: uuid.UUID) -> ClaimEvidence:
        return ClaimEvidence(
            id=uuid.uuid4(),
            claim_version_id=cv_id,
            source_passage_id=self.passage_id,
            role=EvidenceRole.carrying,
            quote="SYNTHETISCH: Beleg.",
        )

    def scope_assignments(
        self, cv_id: uuid.UUID, topic_scope: str = "stationaere_pflege"
    ) -> list[ScopeAssignment]:
        return [
            ScopeAssignment(
                id=uuid.uuid4(),
                claim_version_id=cv_id,
                dimension=ScopeDimension.region,
                value="DE_FEDERAL",
                applies=True,
            ),
            ScopeAssignment(
                id=uuid.uuid4(),
                claim_version_id=cv_id,
                dimension=ScopeDimension.target_group,
                value="relative",
                applies=True,
            ),
            ScopeAssignment(
                id=uuid.uuid4(),
                claim_version_id=cv_id,
                dimension=ScopeDimension.topic,
                value=topic_scope,
                applies=True,
            ),
        ]

    def requires_relation(
        self, from_cv_id: uuid.UUID, to_cv_id: uuid.UUID
    ) -> ClaimRelation:
        return ClaimRelation(
            id=uuid.uuid4(),
            from_claim_version_id=from_cv_id,
            to_claim_version_id=to_cv_id,
            kind=ClaimRelationKind.requires,
            created_at=T_PAST,
        )

    def structured_value(
        self, cv_id: uuid.UUID, value: str = "1000"
    ) -> StructuredValue:
        return StructuredValue(
            id=uuid.uuid4(),
            claim_version_id=cv_id,
            kind=StructuredValueKind.amount_eur,
            value=value,
            unit="EUR",
        )

    async def insert_full_cv(
        self,
        session,
        topic_scope: str = "stationaere_pflege",
        effective_to: datetime | None = None,
        with_structured_value: str | None = None,
    ) -> ClaimVersion:
        """Erstellt eine vollständige published CV (Claim + CV + Evidence + Scopes) und committet."""
        c = self.claim(topic_scope=topic_scope)
        cv = self.published_cv(c.id, effective_to=effective_to)
        evidence = self.carrying_evidence(cv.id)
        scopes = self.scope_assignments(cv.id, topic_scope=topic_scope)
        objects: list = [c, cv, evidence, *scopes]
        if with_structured_value is not None:
            objects.append(self.structured_value(cv.id, value=with_structured_value))
        for obj in objects:
            session.add(obj)
        await session.commit()
        return cv


# ------------------------------------------------------------------ #
# Evidence Builder — Integrationstests                                 #
# ------------------------------------------------------------------ #


async def test_evidence_builder_happy_path(db_clean):
    """Eine published CV mit Beleg → im EvidencePackage."""
    b = _Builder()
    for obj in b.source_objects():
        db_clean.add(obj)
    await db_clean.commit()

    cv = await b.insert_full_cv(db_clean)

    pkg = await build_evidence_package(db_clean, BASE_CTX)

    assert cv.id in pkg.eligible_ids
    assert len(pkg.items) == 1
    assert pkg.items[0].claim_version_id == cv.id
    assert not pkg.excluded_ids


async def test_evidence_builder_expired_cv_excluded(db_clean):
    """Eine abgelaufene CV ist nicht im Package (Gate 3)."""
    b = _Builder()
    for obj in b.source_objects():
        db_clean.add(obj)
    await db_clean.commit()

    # effective_to liegt VOR T_PRESENT → abgelaufen
    cv = await b.insert_full_cv(db_clean, effective_to=T_EXPIRED)

    pkg = await build_evidence_package(db_clean, BASE_CTX)

    assert cv.id not in pkg.eligible_ids
    assert not pkg.items
    assert cv.id not in pkg.excluded_ids  # kein D7-Ausschluss, Gate 3 hat gefiltert


async def test_evidence_builder_d7_requires_ineligible_target_excluded(db_clean):
    """CV A requires CV B (abgelaufen) → A landet in excluded_ids, nicht in eligible_ids."""
    b = _Builder()
    for obj in b.source_objects():
        db_clean.add(obj)
    await db_clean.commit()

    # CV A: eligible
    cv_a = await b.insert_full_cv(db_clean)

    # CV B: abgelaufen (vor T_PRESENT) → nicht eligible
    cv_b = await b.insert_full_cv(db_clean, effective_to=T_EXPIRED)

    # Relation: A requires B
    rel = b.requires_relation(cv_a.id, cv_b.id)
    db_clean.add(rel)
    await db_clean.commit()

    pkg = await build_evidence_package(db_clean, BASE_CTX)

    assert cv_a.id in pkg.excluded_ids, "A muss wegen D7 ausgeschlossen sein"
    assert cv_a.id not in pkg.eligible_ids
    assert cv_b.id not in pkg.eligible_ids  # abgelaufen
    assert not pkg.items


async def test_evidence_builder_d7_requires_eligible_target_both_included(db_clean):
    """CV A requires CV B (beide eligible) → beide im Package."""
    b = _Builder()
    for obj in b.source_objects():
        db_clean.add(obj)
    await db_clean.commit()

    cv_a = await b.insert_full_cv(db_clean)
    cv_b = await b.insert_full_cv(db_clean)

    rel = b.requires_relation(cv_a.id, cv_b.id)
    db_clean.add(rel)
    await db_clean.commit()

    pkg = await build_evidence_package(db_clean, BASE_CTX)

    assert cv_a.id in pkg.eligible_ids
    assert cv_b.id in pkg.eligible_ids
    assert not pkg.excluded_ids
    assert len(pkg.items) == 2


async def test_evidence_builder_conflicting_cv_excluded(db_clean):
    """Eine als conflicting markierte CV ist nicht eligible (Gate 10)."""
    b = _Builder()
    for obj in b.source_objects():
        db_clean.add(obj)
    await db_clean.commit()

    c = b.claim()
    cv = b.published_cv(c.id, conflicting=True)
    evidence = b.carrying_evidence(cv.id)
    scopes = b.scope_assignments(cv.id)
    for obj in [c, cv, evidence, *scopes]:
        db_clean.add(obj)
    await db_clean.commit()

    pkg = await build_evidence_package(db_clean, BASE_CTX)

    assert cv.id not in pkg.eligible_ids


# ------------------------------------------------------------------ #
# Coverage — Integrationstests                                         #
# ------------------------------------------------------------------ #


async def test_coverage_sufficient(db_clean):
    """Alle Aspekte des Intents abgedeckt → sufficient."""
    b = _Builder()
    for obj in b.source_objects():
        db_clean.add(obj)
    await db_clean.commit()

    await b.insert_full_cv(db_clean, topic_scope="stationaere_pflege")

    result = await compute_coverage(db_clean, BASE_CTX, "heimunterbringung")

    assert result.grade == CoverageGrade.sufficient
    assert "stationaere_pflege" in result.covered_aspects
    assert not result.uncovered_aspects


async def test_coverage_partial(db_clean):
    """Nur ein Teil der Aspekte abgedeckt → partial."""
    b = _Builder()
    for obj in b.source_objects():
        db_clean.add(obj)
    await db_clean.commit()

    # Nur stationaere_pflege abgedeckt, nicht finanzierung_pflege
    await b.insert_full_cv(db_clean, topic_scope="stationaere_pflege")

    test_map = {
        "heimunterbringung_multi": ["stationaere_pflege", "finanzierung_pflege"],
    }
    result = await compute_coverage(
        db_clean, BASE_CTX, "heimunterbringung_multi", aspect_map=test_map
    )

    assert result.grade == CoverageGrade.partial
    assert "stationaere_pflege" in result.covered_aspects
    assert "finanzierung_pflege" in result.uncovered_aspects


async def test_coverage_insufficient(db_clean):
    """Kein Aspekt abgedeckt → insufficient."""
    # Keine CVs in der DB
    test_map = {"heimunterbringung": ["stationaere_pflege"]}
    result = await compute_coverage(
        db_clean, BASE_CTX, "heimunterbringung", aspect_map=test_map
    )

    assert result.grade == CoverageGrade.insufficient
    assert not result.covered_aspects
    assert "stationaere_pflege" in result.uncovered_aspects


async def test_coverage_unknown_intent_is_insufficient(db_clean):
    """Unbekannter Intent → insufficient (kein Fallback auf LLM)."""
    result = await compute_coverage(db_clean, BASE_CTX, "unbekannte_lebenslage")

    assert result.grade == CoverageGrade.insufficient
    assert not result.required_aspects


# ------------------------------------------------------------------ #
# Validator — Integrationstests (D8 / Anti-TOCTOU)                   #
# ------------------------------------------------------------------ #


async def test_validator_pass(db_clean):
    """Gültige Aussage mit korrekten StructuredValues → passed."""
    b = _Builder()
    for obj in b.source_objects():
        db_clean.add(obj)
    await db_clean.commit()

    cv = await b.insert_full_cv(db_clean, with_structured_value="1000")

    pkg = await build_evidence_package(db_clean, BASE_CTX)
    assert cv.id in pkg.eligible_ids

    stmt = FactualStatement(
        claim_version_ids=(cv.id,),
        asserted_structured_values=(
            StructuredValueRecord(kind="amount_eur", value="1000", unit="EUR"),
        ),
    )
    report = await validate_statements(db_clean, [stmt], BASE_CTX, pkg)

    assert report.passed
    assert not report.fallback_required
    assert report.fallback_text == ""
    assert report.statement_results[0].passed


async def test_validator_pass_no_structured_values(db_clean):
    """Gültige Aussage ohne StructuredValues-Assertion → passed."""
    b = _Builder()
    for obj in b.source_objects():
        db_clean.add(obj)
    await db_clean.commit()

    cv = await b.insert_full_cv(db_clean)

    pkg = await build_evidence_package(db_clean, BASE_CTX)

    stmt = FactualStatement(
        claim_version_ids=(cv.id,),
        asserted_structured_values=(),
    )
    report = await validate_statements(db_clean, [stmt], BASE_CTX, pkg)

    assert report.passed


async def test_validator_toctou_cv_expired_at_validate_time(db_clean):
    """
    CV ist beim Package-Build noch gültig, aber beim Validieren abgelaufen.
    Validator erkennt den TOCTOU-Gap und schlägt fehl.
    """
    b = _Builder()
    for obj in b.source_objects():
        db_clean.add(obj)
    await db_clean.commit()

    # CV läuft zwischen T_PRESENT und T_LATER ab
    expiry = datetime(2025, 7, 1, tzinfo=timezone.utc)
    cv = await b.insert_full_cv(db_clean, effective_to=expiry)

    # Package-Build zum früheren Zeitpunkt: CV noch gültig
    ctx_build = BASE_CTX  # requested_at = T_PRESENT (2025-06-01)
    pkg = await build_evidence_package(db_clean, ctx_build)
    assert cv.id in pkg.eligible_ids, "CV muss beim Build-Zeitpunkt eligible sein"

    # Validierung zum späteren Zeitpunkt: CV abgelaufen
    ctx_validate = RequestContext(
        requested_at=T_LATER,  # 2025-08-01 > expiry 2025-07-01
        region_id=BASE_CTX.region_id,
        target_group_codes=BASE_CTX.target_group_codes,
        tenant_id=BASE_CTX.tenant_id,
        topic_scope=BASE_CTX.topic_scope,
        locale=BASE_CTX.locale,
    )
    stmt = FactualStatement(claim_version_ids=(cv.id,), asserted_structured_values=())
    report = await validate_statements(db_clean, [stmt], ctx_validate, pkg)

    assert not report.passed
    assert report.fallback_required
    assert report.fallback_text == "Dazu liegen mir keine geprüften Informationen vor."
    result = report.statement_results[0]
    assert not result.passed
    assert "Nicht mehr eligible" in (result.failure_reason or "")


async def test_validator_structured_values_mismatch(db_clean):
    """Behaupteter Wert weicht vom Quellwert ab → fehlgeschlagen."""
    b = _Builder()
    for obj in b.source_objects():
        db_clean.add(obj)
    await db_clean.commit()

    cv = await b.insert_full_cv(db_clean, with_structured_value="1000")

    pkg = await build_evidence_package(db_clean, BASE_CTX)

    # Composer behauptet fälschlicherweise 2000
    stmt = FactualStatement(
        claim_version_ids=(cv.id,),
        asserted_structured_values=(
            StructuredValueRecord(kind="amount_eur", value="2000", unit="EUR"),
        ),
    )
    report = await validate_statements(db_clean, [stmt], BASE_CTX, pkg)

    assert not report.passed
    assert report.fallback_required
    result = report.statement_results[0]
    assert not result.passed
    assert "StructuredValues" in (result.failure_reason or "")


async def test_validator_cv_not_in_package(db_clean):
    """CV wurde nicht ins Package aufgenommen → Validierung schlägt fehl."""
    b = _Builder()
    for obj in b.source_objects():
        db_clean.add(obj)
    await db_clean.commit()

    # Zwei CVs, aber Package für topic_scope der ersten
    cv_a = await b.insert_full_cv(db_clean, topic_scope="stationaere_pflege")
    cv_b = await b.insert_full_cv(db_clean, topic_scope="stationaere_pflege")

    # Package enthält beide, aber wir bauen manuell ein Package das nur cv_a enthält
    from careapp.domain.evidence_builder import EvidencePackage, EvidenceItem
    restricted_pkg = EvidencePackage(
        eligible_ids=frozenset({cv_a.id}),
        items=(),
        excluded_ids=frozenset(),
    )

    # Aussage referenziert cv_b, das nicht im restricted_pkg ist
    stmt = FactualStatement(claim_version_ids=(cv_b.id,), asserted_structured_values=())
    report = await validate_statements(db_clean, [stmt], BASE_CTX, restricted_pkg)

    assert not report.passed
    result = report.statement_results[0]
    assert not result.passed
    assert "nicht im Evidence Package" in (result.failure_reason or "")


async def test_validator_unknown_cv_id_fails(db_clean):
    """Unbekannte CV-ID → Validator meldet Fehler."""
    from careapp.domain.evidence_builder import EvidencePackage

    unknown_id = uuid.uuid4()
    empty_pkg = EvidencePackage(
        eligible_ids=frozenset({unknown_id}),
        items=(),
        excluded_ids=frozenset(),
    )
    stmt = FactualStatement(claim_version_ids=(unknown_id,), asserted_structured_values=())
    report = await validate_statements(db_clean, [stmt], BASE_CTX, empty_pkg)

    assert not report.passed
    assert "nicht in DB" in (report.statement_results[0].failure_reason or "")
