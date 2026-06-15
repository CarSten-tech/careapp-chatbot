"""
Deterministischer Eligibility-Filter (Layer 2, §4.1).

Reiner Anwendungscode — kein LLM, keine Datenbankabfragen.
Alle 10 Gates müssen bestehen. Unbekannte Werte → false (D4).
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class EligibilityResult(Enum):
    ELIGIBLE = "eligible"
    NOT_ELIGIBLE = "not_eligible"


@dataclass(frozen=True)
class RequestContext:
    requested_at: datetime
    region_id: Optional[str]
    target_group_codes: tuple[str, ...]
    tenant_id: Optional[str]
    topic_scope: str
    locale: str


@dataclass(frozen=True)
class ClaimVersionSnapshot:
    """Unveränderlicher Schnappschuss einer ClaimVersion für die Eligibility-Prüfung."""
    id: str
    status: str
    region_binding: str  # "region_independent" | "region_specific"
    effective_from: Optional[datetime]
    effective_to: Optional[datetime]
    published_at: Optional[datetime]
    unpublished_at: Optional[datetime]
    tenant_visibility: Optional[str]
    conflicting: bool


@dataclass(frozen=True)
class ScopeAssignmentSnapshot:
    dimension: str  # "region" | "target_group" | "topic"
    value: str
    applies: bool


@dataclass(frozen=True)
class EvidenceSnapshot:
    role: str  # "carrying" | "supporting" | "contextual"
    passage_exists: bool


@dataclass(frozen=True)
class EligibilityCheck:
    result: EligibilityResult
    failed_gate: Optional[int]
    reason: Optional[str]

    @property
    def is_eligible(self) -> bool:
        return self.result == EligibilityResult.ELIGIBLE


_ELIGIBLE = EligibilityCheck(EligibilityResult.ELIGIBLE, None, None)


def _fail(gate: int, reason: str) -> EligibilityCheck:
    return EligibilityCheck(EligibilityResult.NOT_ELIGIBLE, gate, reason)


def is_answer_eligible(
    cv: ClaimVersionSnapshot,
    scopes: list[ScopeAssignmentSnapshot],
    evidences: list[EvidenceSnapshot],
    ctx: RequestContext,
) -> EligibilityCheck:
    """
    Prüft alle 10 Gates in definierter Reihenfolge.
    Gibt beim ersten fehlgeschlagenen Gate zurück (kein Short-Circuit nach oben).
    """

    # Gate 1: muss published sein
    if cv.status != "published":
        return _fail(1, f"status={cv.status!r} != published")

    # Gate 2: published_at und effective_from müssen gesetzt sein
    if cv.published_at is None or cv.effective_from is None:
        return _fail(2, "published_at or effective_from is None")

    # Gate 3: requested_at im Gültigkeitsfenster
    if ctx.requested_at < cv.effective_from:
        return _fail(3, "requested_at < effective_from")
    if cv.effective_to is not None and ctx.requested_at >= cv.effective_to:
        return _fail(3, "requested_at >= effective_to")

    # Gate 4: nicht bereits zurückgezogen (unpublished_at)
    if cv.unpublished_at is not None and ctx.requested_at >= cv.unpublished_at:
        return _fail(4, "requested_at >= unpublished_at")

    # Gate 5: Region (D6 – zweiklassiges Modell)
    if cv.region_binding == "region_specific":
        if ctx.region_id is None:
            return _fail(5, "region_specific claim but region_id unknown in context")
        region_values = {s.value for s in scopes if s.dimension == "region" and s.applies}
        if ctx.region_id not in region_values and "DE_FEDERAL" not in region_values:
            return _fail(5, f"region {ctx.region_id!r} not in {region_values}")
    # region_independent: kein Regions-Check nötig

    # Gate 6: Zielgruppe
    tg_scopes = [s for s in scopes if s.dimension == "target_group" and s.applies]
    if tg_scopes:
        tg_values = {s.value for s in tg_scopes}
        if not tg_values.intersection(ctx.target_group_codes):
            return _fail(6, f"target_groups {ctx.target_group_codes} not in {tg_values}")

    # Gate 7: Themenbereich
    topic_scopes = [s for s in scopes if s.dimension == "topic" and s.applies]
    if topic_scopes:
        topic_values = {s.value for s in topic_scopes}
        if ctx.topic_scope not in topic_values:
            return _fail(7, f"topic_scope {ctx.topic_scope!r} not in {topic_values}")

    # Gate 8: Mandantensichtbarkeit
    if cv.tenant_visibility is not None:
        if ctx.tenant_id is None:
            return _fail(8, "tenant-restricted claim but tenant_id unknown in context")
        if ctx.tenant_id != cv.tenant_visibility:
            return _fail(8, f"tenant_id {ctx.tenant_id!r} != {cv.tenant_visibility!r}")

    # Gate 9: mindestens ein carrying-Beleg mit existenter Passage
    carrying = [e for e in evidences if e.role == "carrying" and e.passage_exists]
    if not carrying:
        return _fail(9, "no carrying evidence with existing passage")

    # Gate 10: nicht conflicting, withdrawn oder superseded
    if cv.conflicting:
        return _fail(10, "claim is marked conflicting")
    if cv.status in ("withdrawn", "superseded"):
        return _fail(10, f"claim status is {cv.status!r}")

    return _ELIGIBLE
