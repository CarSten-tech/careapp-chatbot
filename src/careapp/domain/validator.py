"""
Post-Generation-Validator (Layer 2, §4.4 / D8).

Tragende Invariante: Vertraut der Composer-Ausgabe nichts.
Lädt ClaimVersions frisch aus der DB (Anti-TOCTOU), prüft Eligibility
erneut zum Ausgabezeitpunkt und vergleicht StructuredValues gegen die Quelle.

Fehlerverhalten (§4.5): Ein Fehler → passed=False, fallback_required=True.
Fallback-Wortlaut fest verdrahtet. Kein LLM-Judge hier.
"""

import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from careapp.db.models.claim import ClaimEvidence, ClaimVersion
from careapp.domain.eligibility import RequestContext, is_answer_eligible
from careapp.domain.evidence_builder import (
    EvidencePackage,
    StructuredValueRecord,
    _cv_to_snapshot,
    _evidence_to_snapshot,
    _scope_to_snapshot,
)

FALLBACK_TEXT = "Dazu liegen mir keine geprüften Informationen vor."


@dataclass(frozen=True)
class FactualStatement:
    """Eine fachliche Aussage aus dem Composer — Behauptung, noch kein Beleg."""

    claim_version_ids: tuple[uuid.UUID, ...]
    asserted_structured_values: tuple[StructuredValueRecord, ...]


@dataclass(frozen=True)
class StatementValidation:
    claim_version_id: uuid.UUID
    passed: bool
    failure_reason: Optional[str]


@dataclass(frozen=True)
class ValidationReport:
    passed: bool
    statement_results: tuple[StatementValidation, ...]
    fallback_required: bool
    fallback_text: str


async def validate_statements(
    session: AsyncSession,
    statements: list[FactualStatement],
    ctx: RequestContext,
    evidence_package: EvidencePackage,
) -> ValidationReport:
    """
    Prüft alle FactualStatements des Composers deterministisch.

    Pro CV-ID:
      1. Frisch aus DB laden (Anti-TOCTOU, D8)
      2. Eligibility erneut zum Ausgabezeitpunkt prüfen
      3. Mitgliedschaft im EvidencePackage verifizieren
      4. StructuredValues exakt gegen Quelle vergleichen (D3)
    """
    results: list[StatementValidation] = []
    for stmt in statements:
        for cv_id in stmt.claim_version_ids:
            results.append(
                await _validate_cv(session, cv_id, stmt, ctx, evidence_package)
            )

    passed = all(r.passed for r in results)
    return ValidationReport(
        passed=passed,
        statement_results=tuple(results),
        fallback_required=not passed,
        fallback_text=FALLBACK_TEXT if not passed else "",
    )


async def _validate_cv(
    session: AsyncSession,
    cv_id: uuid.UUID,
    stmt: FactualStatement,
    ctx: RequestContext,
    package: EvidencePackage,
) -> StatementValidation:
    # D8: frisch laden, kein ORM-Cache verwenden
    db_result = await session.execute(
        select(ClaimVersion)
        .where(ClaimVersion.id == cv_id)
        .options(
            selectinload(ClaimVersion.claim),
            selectinload(ClaimVersion.scope_assignments),
            selectinload(ClaimVersion.evidences).selectinload(ClaimEvidence.passage),
            selectinload(ClaimVersion.structured_values),
        )
    )
    cv = db_result.scalar_one_or_none()

    if cv is None:
        return StatementValidation(cv_id, False, "ClaimVersion nicht in DB gefunden")

    # Eligibility erneut prüfen (Anti-TOCTOU: Zeitpunkt kann sich seit Package-Build geändert haben)
    snapshot = _cv_to_snapshot(cv)
    scopes = [_scope_to_snapshot(s) for s in cv.scope_assignments]
    evidences_snap = [_evidence_to_snapshot(e) for e in cv.evidences]
    check = is_answer_eligible(snapshot, scopes, evidences_snap, ctx)
    if not check.is_eligible:
        return StatementValidation(cv_id, False, f"Nicht mehr eligible: {check.reason}")

    # Mitgliedschaft im EvidencePackage (D8)
    if cv_id not in package.eligible_ids:
        return StatementValidation(cv_id, False, "CV nicht im Evidence Package enthalten")

    # StructuredValues exakt vergleichen (D3)
    if stmt.asserted_structured_values:
        source_svs = frozenset(
            StructuredValueRecord(
                kind=sv.kind.value if hasattr(sv.kind, "value") else sv.kind,
                value=sv.value,
                unit=sv.unit,
            )
            for sv in cv.structured_values
        )
        asserted = frozenset(stmt.asserted_structured_values)
        if asserted != source_svs:
            return StatementValidation(
                cv_id,
                False,
                f"StructuredValues stimmen nicht überein: behauptet={asserted}, Quelle={source_svs}",
            )

    return StatementValidation(cv_id, True, None)
