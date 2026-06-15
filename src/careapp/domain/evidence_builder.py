"""
Evidence Builder (Layer 2, §4.2 / D7).
Reiner Anwendungscode — kein LLM.

Ablauf:
  1. Alle ClaimVersions aus DB laden
  2. Eligibility-Filter (§4.1) anwenden
  3. D7 prüfen: requires/exception_to-Ziel muss ebenfalls eligible sein
  4. Nur IDs und gefrorene Belegtexte zurückgeben

Pilot-Einschränkung D7: Ziel-CVs werden nur innerhalb des geladenen Sets geprüft
(gleicher topic_scope). Cross-Topic-Relationen gelten konservativ als nicht erfüllbar.
"""

import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from careapp.db.models.claim import (
    ClaimEvidence,
    ClaimRelationKind,
    ClaimVersion,
)
from careapp.domain.eligibility import (
    ClaimVersionSnapshot,
    EvidenceSnapshot,
    RequestContext,
    ScopeAssignmentSnapshot,
    is_answer_eligible,
)


@dataclass(frozen=True)
class StructuredValueRecord:
    kind: str
    value: str
    unit: Optional[str]


@dataclass(frozen=True)
class EvidenceItem:
    """Gefrorener Belegtext — nur IDs und Zitate, keine freien Dokumentinhalte."""

    claim_version_id: uuid.UUID
    statement_text: str
    carrying_quote: str
    structured_values: tuple[StructuredValueRecord, ...]


@dataclass(frozen=True)
class EvidencePackage:
    eligible_ids: frozenset[uuid.UUID]
    items: tuple[EvidenceItem, ...]
    excluded_ids: frozenset[uuid.UUID]  # D7-Ausschlüsse


def _cv_to_snapshot(cv: ClaimVersion) -> ClaimVersionSnapshot:
    rb = cv.claim.region_binding
    return ClaimVersionSnapshot(
        id=str(cv.id),
        status=cv.status.value if hasattr(cv.status, "value") else cv.status,
        region_binding=rb.value if hasattr(rb, "value") else rb,
        effective_from=cv.effective_from,
        effective_to=cv.effective_to,
        published_at=cv.published_at,
        unpublished_at=cv.unpublished_at,
        tenant_visibility=cv.tenant_visibility,
        conflicting=cv.conflicting,
    )


def _scope_to_snapshot(s) -> ScopeAssignmentSnapshot:
    dim = s.dimension
    return ScopeAssignmentSnapshot(
        dimension=dim.value if hasattr(dim, "value") else dim,
        value=s.value,
        applies=s.applies,
    )


def _evidence_to_snapshot(e) -> EvidenceSnapshot:
    role = e.role
    return EvidenceSnapshot(
        role=role.value if hasattr(role, "value") else role,
        passage_exists=e.passage is not None,
    )


async def build_evidence_package(
    session: AsyncSession,
    ctx: RequestContext,
) -> EvidencePackage:
    """
    Lädt alle ClaimVersions, filtert nach Eligibility und wendet D7 an.

    Gibt ein unveränderliches EvidencePackage zurück. Enthält ausschließlich
    IDs und gefrorene Belegtexte — keine freien Dokumentinhalte.
    """
    result = await session.execute(
        select(ClaimVersion).options(
            selectinload(ClaimVersion.claim),
            selectinload(ClaimVersion.scope_assignments),
            selectinload(ClaimVersion.evidences).selectinload(ClaimEvidence.passage),
            selectinload(ClaimVersion.structured_values),
            selectinload(ClaimVersion.outgoing_relations),
        )
    )
    all_cvs: list[ClaimVersion] = list(result.scalars().unique())

    # Schritt 1: Eligibility-Filter (alle 10 Gates, §4.1)
    eligible_cvs: dict[uuid.UUID, ClaimVersion] = {}
    for cv in all_cvs:
        snapshot = _cv_to_snapshot(cv)
        scopes = [_scope_to_snapshot(s) for s in cv.scope_assignments]
        evidences = [_evidence_to_snapshot(e) for e in cv.evidences]
        if is_answer_eligible(snapshot, scopes, evidences, ctx).is_eligible:
            eligible_cvs[cv.id] = cv

    # Schritt 2: D7 — requires/exception_to-Ziel muss ebenfalls eligible sein
    eligible_ids: set[uuid.UUID] = set(eligible_cvs.keys())
    excluded_ids: set[uuid.UUID] = set()
    for cv_id, cv in list(eligible_cvs.items()):
        for rel in cv.outgoing_relations:
            if rel.kind in (ClaimRelationKind.requires, ClaimRelationKind.exception_to):
                if rel.to_claim_version_id not in eligible_ids:
                    excluded_ids.add(cv_id)
                    break

    final_ids = eligible_ids - excluded_ids

    # Schritt 3: EvidenceItems bauen (nur ID + gefrorene Texte)
    items: list[EvidenceItem] = []
    for cv_id in final_ids:
        cv = eligible_cvs[cv_id]
        carrying = next(
            (
                e
                for e in cv.evidences
                if (e.role.value if hasattr(e.role, "value") else e.role) == "carrying"
                and e.passage is not None
            ),
            None,
        )
        if carrying is None:
            continue
        svs = tuple(
            StructuredValueRecord(
                kind=sv.kind.value if hasattr(sv.kind, "value") else sv.kind,
                value=sv.value,
                unit=sv.unit,
            )
            for sv in cv.structured_values
        )
        items.append(
            EvidenceItem(
                claim_version_id=cv_id,
                statement_text=cv.statement_text,
                carrying_quote=carrying.quote,
                structured_values=svs,
            )
        )

    return EvidencePackage(
        eligible_ids=frozenset(final_ids),
        items=tuple(items),
        excluded_ids=frozenset(excluded_ids),
    )
