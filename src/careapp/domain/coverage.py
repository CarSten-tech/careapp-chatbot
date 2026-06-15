"""
Coverage-Bewertung (Layer 2, §4.3).

ASPECT_MAP ist redaktionell gepflegt — niemals LLM-generiert.
Jeder Eintrag: resolved_intent → Liste von topic_scope-Aspekten.

sufficient    : alle Aspekte durch mindestens eine eligible carrying-CV abgedeckt
partial       : einige, aber nicht alle Aspekte abgedeckt
insufficient  : kein Aspekt abgedeckt (oder intent unbekannt)
"""

import dataclasses
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from careapp.domain.eligibility import RequestContext
from careapp.domain.evidence_builder import EvidencePackage, build_evidence_package

# Redaktionell gepflegte Aspektkarte (Pilot: Kreis Neuss / Düsseldorf, NRW)
# Erweiterung nur durch Fachredaktion — nicht zur Laufzeit veränderbar.
ASPECT_MAP: dict[str, list[str]] = {
    "heimunterbringung": [
        "stationaere_pflege",
    ],
}


class CoverageGrade(str, Enum):
    sufficient = "sufficient"
    partial = "partial"
    insufficient = "insufficient"


@dataclass
class CoverageResult:
    grade: CoverageGrade
    required_aspects: frozenset[str]
    covered_aspects: frozenset[str]
    uncovered_aspects: frozenset[str]
    packages: dict[str, EvidencePackage]  # aspect → EvidencePackage


async def compute_coverage(
    session: AsyncSession,
    ctx_base: RequestContext,
    resolved_intent: str,
    aspect_map: Optional[dict[str, list[str]]] = None,
) -> CoverageResult:
    """
    Berechnet Coverage-Grad für einen resolved_intent.

    Für jeden Aspekt wird ein separates EvidencePackage gebaut
    (ctx_base mit topic_scope = Aspekt-topic_scope). So bleibt
    Gate 7 korrekt und die Aspekte bleiben unabhängig prüfbar.

    aspect_map-Parameter für Tests; Produktion nutzt ASPECT_MAP.
    """
    _map = aspect_map if aspect_map is not None else ASPECT_MAP
    required = frozenset(_map.get(resolved_intent, []))

    if not required:
        return CoverageResult(
            grade=CoverageGrade.insufficient,
            required_aspects=frozenset(),
            covered_aspects=frozenset(),
            uncovered_aspects=frozenset(),
            packages={},
        )

    covered: set[str] = set()
    packages: dict[str, EvidencePackage] = {}

    for aspect in required:
        aspect_ctx = dataclasses.replace(ctx_base, topic_scope=aspect)
        pkg = await build_evidence_package(session, aspect_ctx)
        packages[aspect] = pkg
        if pkg.eligible_ids:
            covered.add(aspect)

    uncovered = required - covered

    if covered == required:
        grade = CoverageGrade.sufficient
    elif covered:
        grade = CoverageGrade.partial
    else:
        grade = CoverageGrade.insufficient

    return CoverageResult(
        grade=grade,
        required_aspects=required,
        covered_aspects=frozenset(covered),
        uncovered_aspects=frozenset(uncovered),
        packages=packages,
    )
