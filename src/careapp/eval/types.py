"""
Golden-Test-Set-Typen (Layer 5 §1).

`EvalCase`   — formaler Testfall: Kategorie, Beschreibung, Erwartungen, Hard-Gate-Constraints.
`EvalResult` — deterministisch auswertbares Ergebnis eines Testlaufs.
`EvalMetrics`— aggregierte Metriken über den gesamten Testlauf (§2).

Seeding und LLM-Fake-Antworten liegen in der Testdatei, nicht im EvalCase —
so bleiben die Fälle reproduzierbar ohne Zustand in den Typen.
"""

import uuid
from dataclasses import dataclass, field
from typing import Optional

from careapp.orchestration.state import Disposition


class HardGateViolation(AssertionError):
    """Raised wenn ein hartes Gate (§3) verletzt ist. Blocking in CI."""


@dataclass(frozen=True)
class EvalCase:
    """
    Formaler Testfall (§1.1). Enthält Kategorie-Metadaten und deterministisch
    prüfbare Erwartungen — analog zum JSON-Format aus §1.1 (JSON-Serialisierung: Welle 5b).

    Kategorien C1–C17 (§1.2): jede Kategorie prüft eine andere Sicherheitseigenschaft.
    """

    id: str               # "gc-c01" etc.
    category: str         # "C1".."C17"
    description: str      # Menschenlesbare Beschreibung
    expected_disposition: Disposition  # Erwartetes Verhalten

    # Hard-Gate-Constraints
    forbidden_cv_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)
    # CVs die NICHT in evidence_claim_version_ids erscheinen dürfen (C6-C8)
    forbidden_block_types: frozenset[str] = field(default_factory=frozenset)
    # Block-Typen die NICHT im final_response erscheinen dürfen
    expected_fail_closed: bool = False
    # True = muss in Fallback/Handoff enden, nie in freier Antwort (C17)


@dataclass(frozen=True)
class EvalResult:
    """
    Deterministisch auswertbares Ergebnis eines Testlaufs.
    Alle Flag-Felder: True = Verletzung (Gates gerissen).
    """

    case: EvalCase
    disposition: Optional[Disposition]
    evidence_cv_ids: frozenset[uuid.UUID]
    final_block_types: frozenset[str]
    fallback_reason: Optional[str]
    audit_present: bool

    # Versions-Tripel aus dem Audit (§4: Tests an Tripel gebunden)
    graph_version: Optional[str] = None
    prompt_set_version: Optional[str] = None
    model_version: Optional[str] = None

    # Hard-Gate-Flags (§3)
    unsupported_claim_found: bool = False
    forbidden_cv_appeared: bool = False      # verbotene CV in evidence_cv_ids
    forbidden_block_appeared: bool = False   # verbotener Block-Typ in final_response
    disposition_mismatch: bool = False       # falsche Disposition
    fail_closed_violated: bool = False       # C17: kein Fail-Closed trotz Pflicht

    @property
    def any_hard_gate_violated(self) -> bool:
        return (
            self.unsupported_claim_found
            or self.forbidden_cv_appeared
            or self.forbidden_block_appeared
            or self.disposition_mismatch
            or self.fail_closed_violated
        )


@dataclass(frozen=True)
class EvalMetrics:
    """
    Aggregierte Metriken (§2) über einen Volllauf des Golden Test Set.
    Harte Gates (§3) sind binär; weiche Gates als Quoten berichtbar.

    `graph_versions` enthält alle im Lauf gesehenen Graph-Versionen — sollte
    genau ein Element enthalten. Mehr als eines zeigt einen Versions-Mismatch an
    (§4: Regressionslauf bei Modell-/Prompt-Wechsel).
    """

    total_cases: int
    hard_gate_violations: int

    # §2-Metriken (auswählbare Harte Gates)
    unsupported_claim_rate: float   # = 0 (hart)
    forbidden_cv_rate: float        # = 0 (hart)
    adversarial_pass_rate: float    # C10–C12, C15–C16: = 100 % (hart)
    fail_closed_rate: float         # C17: = 100 % (hart)

    # Weiche Metriken
    disposition_accuracy: float     # korrekte Disposition / Gesamt

    hard_gates_passed: bool
    violations: tuple[str, ...]

    # Versions-Tripel (§4)
    graph_versions: frozenset[str] = field(default_factory=frozenset)
    prompt_set_versions: frozenset[str] = field(default_factory=frozenset)
    model_versions: frozenset[str] = field(default_factory=frozenset)
