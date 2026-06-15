"""
§5.1 Pilot-Eintrittscheckliste — ausführbare Assertions (Layer 5).

Jeder Test prüft ein konkretes Eintritts-Kriterium für den Pilot-Start.
Alle Tests sind offline (kein DB, kein Live-LLM).
Marker: @pytest.mark.pilot_entry — blocking CI-Job.

PE-01  Consent-Gate vor jedem LLM-Node (statische Kante SESSION_START → CONSENT)
PE-02  SESSION_START kann SAFETY nicht direkt erreichen (kein Bypass)
PE-03  Fail-Closed-Dispositions decken alle sicheren Ausgänge ab (§7)
PE-04  Input-Größenlimit konfiguriert und > 0 (L4-4)
PE-05  Rate-Limit konfiguriert und > 0 (L4-4)
PE-06  EvalResult trägt Versions-Tripel-Felder (§4)
PE-07  EvalMetrics aggregiert Versions-Mengen aus Ergebnisliste (§4)
PE-08  Versions-Mismatch in EvalMetrics erkennbar (§4)
PE-09  check_hard_gates() wirft HardGateViolation bei Disposition-Mismatch (§3)
PE-10  compute_metrics() leere Suite: hard_gates_passed = True (Robustheit)
PE-11  Architektur-Dokumente für alle Layer vorhanden (vollständige Spec)
"""

import dataclasses
import uuid
from pathlib import Path

import pytest

from careapp.eval.runner import (
    _FAIL_CLOSED_DISPOSITIONS,
    check_hard_gates,
    compute_metrics,
)
from careapp.eval.types import EvalCase, EvalMetrics, EvalResult, HardGateViolation
from careapp.orchestration.graph import ALLOWED_EDGES, CONSENT, SAFETY, SESSION_START
from careapp.orchestration.state import Disposition, SessionBudgets

pytestmark = pytest.mark.pilot_entry

# ──────────────────────────────────────────────────────────────────────────────
# Hilfsfunktionen
# ──────────────────────────────────────────────────────────────────────────────

_DOCS = Path(__file__).parent.parent.parent / "docs" / "chatbot"


def _case(
    disposition: Disposition = Disposition.no_verified_information,
    category: str = "C1",
) -> EvalCase:
    return EvalCase(
        id=f"gc-pe-{category.lower()}",
        category=category,
        description="pilot-checklist fixture",
        expected_disposition=disposition,
    )


def _result(
    case: EvalCase,
    *,
    disposition: Disposition | None = None,
    graph_version: str | None = "graph-v1",
    prompt_set_version: str | None = "prompts-v1",
    model_version: str | None = "claude-haiku-4-5",
    **overrides: object,
) -> EvalResult:
    return EvalResult(
        case=case,
        disposition=disposition if disposition is not None else case.expected_disposition,
        evidence_cv_ids=frozenset(),
        final_block_types=frozenset(),
        fallback_reason=None,
        audit_present=True,
        graph_version=graph_version,
        prompt_set_version=prompt_set_version,
        model_version=model_version,
        **overrides,  # type: ignore[arg-type]
    )


# ──────────────────────────────────────────────────────────────────────────────
# PE-01: Consent-Gate in statischen Kanten verankert
# ──────────────────────────────────────────────────────────────────────────────

def test_pe01_consent_reachable_from_session_start():
    """SESSION_START → CONSENT muss als erlaubte Kante existieren."""
    assert CONSENT in ALLOWED_EDGES[SESSION_START], (
        "Consent-Gate fehlt: SESSION_START kann CONSENT nicht erreichen"
    )


# ──────────────────────────────────────────────────────────────────────────────
# PE-02: SAFETY nie direkt von SESSION_START erreichbar
# ──────────────────────────────────────────────────────────────────────────────

def test_pe02_no_direct_safety_bypass():
    """SESSION_START darf SAFETY nicht direkt erreichen — Consent-Gate würde umgangen."""
    session_start_targets = ALLOWED_EDGES.get(SESSION_START, frozenset())
    assert SAFETY not in session_start_targets, (
        "Sicherheitslücke: SESSION_START kann SAFETY ohne Consent erreichen"
    )


# ──────────────────────────────────────────────────────────────────────────────
# PE-03: Fail-Closed-Dispositions decken alle sicheren Ausgänge ab (§7)
# ──────────────────────────────────────────────────────────────────────────────

def test_pe03_fail_closed_dispositions_complete():
    """§7 definiert drei sichere Ausgangsdispositionen — alle müssen abgedeckt sein."""
    required = {
        Disposition.no_verified_information,
        Disposition.safe_scope_response,
        Disposition.human_handoff,
    }
    assert required <= _FAIL_CLOSED_DISPOSITIONS, (
        f"Fehlende Fail-Closed-Dispositionen: {required - _FAIL_CLOSED_DISPOSITIONS}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# PE-04: Input-Größenlimit konfiguriert (L4-4)
# ──────────────────────────────────────────────────────────────────────────────

def test_pe04_input_size_limit_configured():
    """SessionBudgets.max_user_message_chars > 0 — L4-4 Guard aktiv."""
    budgets = SessionBudgets()
    assert budgets.max_user_message_chars > 0, "max_user_message_chars nicht konfiguriert"


def test_pe04_input_size_limit_reasonable():
    """Standard-Limit ≤ 10.000 Zeichen — kein triviales Nicht-Limit."""
    budgets = SessionBudgets()
    assert budgets.max_user_message_chars <= 10_000


# ──────────────────────────────────────────────────────────────────────────────
# PE-05: Rate-Limit konfiguriert (L4-4)
# ──────────────────────────────────────────────────────────────────────────────

def test_pe05_rate_limit_configured():
    """SessionBudgets.max_turns_per_session > 0 — L4-4 Rate-Limit aktiv."""
    budgets = SessionBudgets()
    assert budgets.max_turns_per_session > 0, "max_turns_per_session nicht konfiguriert"


def test_pe05_rate_limit_reasonable():
    """Standard-Limit ≤ 100 Turns — kein triviales Nicht-Limit."""
    budgets = SessionBudgets()
    assert budgets.max_turns_per_session <= 100


# ──────────────────────────────────────────────────────────────────────────────
# PE-06: EvalResult trägt Versions-Tripel-Felder (§4)
# ──────────────────────────────────────────────────────────────────────────────

def test_pe06_eval_result_has_version_fields():
    """EvalResult muss graph_version, prompt_set_version, model_version tragen (§4)."""
    fields = {f.name for f in dataclasses.fields(EvalResult)}
    assert "graph_version" in fields
    assert "prompt_set_version" in fields
    assert "model_version" in fields


def test_pe06_eval_result_version_defaults_none():
    """Versions-Tripel defaulten auf None — kompatibel mit Ergebnissen ohne Audit."""
    case = _case()
    r = EvalResult(
        case=case,
        disposition=case.expected_disposition,
        evidence_cv_ids=frozenset(),
        final_block_types=frozenset(),
        fallback_reason=None,
        audit_present=False,
    )
    assert r.graph_version is None
    assert r.prompt_set_version is None
    assert r.model_version is None


# ──────────────────────────────────────────────────────────────────────────────
# PE-07: EvalMetrics aggregiert Versions-Mengen (§4)
# ──────────────────────────────────────────────────────────────────────────────

def test_pe07_eval_metrics_has_version_sets():
    """EvalMetrics muss graph_versions, prompt_set_versions, model_versions enthalten (§4)."""
    fields = {f.name for f in dataclasses.fields(EvalMetrics)}
    assert "graph_versions" in fields
    assert "prompt_set_versions" in fields
    assert "model_versions" in fields


def test_pe07_compute_metrics_collects_versions():
    """compute_metrics() muss alle Versions-Tripel der Ergebnisse sammeln."""
    case = _case()
    results = [_result(case, graph_version="graph-v1")]
    metrics = compute_metrics(results)
    assert "graph-v1" in metrics.graph_versions
    assert "prompts-v1" in metrics.prompt_set_versions
    assert "claude-haiku-4-5" in metrics.model_versions


# ──────────────────────────────────────────────────────────────────────────────
# PE-08: Versions-Mismatch in EvalMetrics erkennbar (§4)
# ──────────────────────────────────────────────────────────────────────────────

def test_pe08_version_mismatch_visible_in_metrics():
    """
    Wenn zwei Ergebnisse verschiedene graph_versions tragen, muss
    compute_metrics() beide in graph_versions sichtbar machen.
    Damit ist ein unbeabsichtigter Modell-/Prompt-Wechsel im Lauf erkennbar.
    """
    case = _case()
    results = [
        _result(case, graph_version="graph-v1"),
        _result(case, graph_version="graph-v2"),
    ]
    metrics = compute_metrics(results)
    assert len(metrics.graph_versions) == 2, (
        f"Versions-Mismatch nicht erkannt: graph_versions={metrics.graph_versions}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# PE-09: check_hard_gates() wirft HardGateViolation bei Disposition-Mismatch (§3)
# ──────────────────────────────────────────────────────────────────────────────

def test_pe09_hard_gate_raises_on_disposition_mismatch():
    """§3 Hard Gate: falsche Disposition → HardGateViolation (blocking in CI)."""
    case = _case(disposition=Disposition.no_verified_information)
    result = _result(
        case,
        disposition=Disposition.presented,
        disposition_mismatch=True,
    )
    with pytest.raises(HardGateViolation):
        check_hard_gates(result)


def test_pe09_hard_gate_passes_on_correct_disposition():
    """§3 Hard Gate: korrekte Disposition → keine Exception."""
    case = _case(disposition=Disposition.no_verified_information)
    result = _result(case)
    check_hard_gates(result)  # darf nicht werfen


# ──────────────────────────────────────────────────────────────────────────────
# PE-10: compute_metrics() leere Suite → hard_gates_passed = True
# ──────────────────────────────────────────────────────────────────────────────

def test_pe10_empty_suite_passes_gates():
    """compute_metrics([]) muss hard_gates_passed=True liefern — keine Nulldivision."""
    metrics = compute_metrics([])
    assert metrics.hard_gates_passed is True
    assert metrics.total_cases == 0


# ──────────────────────────────────────────────────────────────────────────────
# PE-11: Architektur-Dokumente für alle Layer vorhanden
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("doc", [
    "architecture-knowledge-and-control-core.md",
    "architecture-llm-layers-and-threat-model.md",
    "architecture-orchestration.md",
    "architecture-evaluation-and-pilot.md",
    "architecture-clients.md",
    "HANDOVER.md",
    "open-decisions.md",
])
def test_pe11_architecture_docs_exist(doc: str):
    """Vollständige Architekturdokumentation muss vor Pilot-Start vorliegen."""
    path = _DOCS / doc
    assert path.exists(), f"Pflichtdokument fehlt: docs/chatbot/{doc}"
