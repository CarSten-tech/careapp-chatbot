"""
Tests für die Scope/Safety-Entscheidung (Layer 3, §2 LLM-1 + DoD).

Kernprinzip: Die LLM-Klassifikation darf nur VERSCHÄRFEN, nie erlauben.
Reine Python-Logik — kein LLM, keine DB.
"""

from careapp.llm.scope_safety import (
    DeterministicSignals,
    SafetyDisposition,
    decide_scope_safety,
)
from careapp.llm.schemas import ScopeSafetyClassification


def _classification(**overrides) -> ScopeSafetyClassification:
    base = dict(
        in_scope=True,
        requires_diagnosis_triage_treatment=False,
        requires_individual_eligibility_decision=False,
        safety_signal=False,
        prompt_injection_suspected=False,
        confidence=0.9,
        safety_notice_id=None,
    )
    base.update(overrides)
    return ScopeSafetyClassification(**base)


IN_SCOPE_SIGNALS = DeterministicSignals(topic_in_allowed_scope=True)


def test_happy_path_proceed():
    decision = decide_scope_safety(_classification(), IN_SCOPE_SIGNALS)
    assert decision.disposition == SafetyDisposition.proceed


def test_parse_error_is_safe_fallback():
    """Keine Klassifikation (Parsefehler) → konservativer Fallback."""
    decision = decide_scope_safety(None, IN_SCOPE_SIGNALS)
    assert decision.disposition == SafetyDisposition.safe_fallback


def test_llm_cannot_grant_scope_rules_deny():
    """LLM hält 'in scope', aber Regel sagt: Thema außerhalb Scope → out_of_scope."""
    signals = DeterministicSignals(topic_in_allowed_scope=False)
    decision = decide_scope_safety(_classification(in_scope=True), signals)
    assert decision.disposition == SafetyDisposition.out_of_scope
    assert "rule" in decision.reason


def test_llm_can_tighten_scope():
    """Regel erlaubt Thema, aber LLM hält out of scope → out_of_scope (Verschärfung)."""
    decision = decide_scope_safety(_classification(in_scope=False), IN_SCOPE_SIGNALS)
    assert decision.disposition == SafetyDisposition.out_of_scope


def test_hard_safety_trigger_with_approved_notice():
    signals = DeterministicSignals(
        topic_in_allowed_scope=True,
        hard_safety_trigger=True,
        approved_safety_notice_ids=frozenset({"krisennotruf_de"}),
    )
    decision = decide_scope_safety(
        _classification(safety_notice_id="krisennotruf_de"), signals
    )
    assert decision.disposition == SafetyDisposition.safety_notice
    assert decision.safety_notice_id == "krisennotruf_de"


def test_safety_signal_without_approved_notice_falls_back():
    """Safety-Signal, aber kein freigegebener Baustein wählbar → sicherer Fallback."""
    signals = DeterministicSignals(
        topic_in_allowed_scope=True,
        approved_safety_notice_ids=frozenset({"krisennotruf_de"}),
    )
    decision = decide_scope_safety(
        _classification(safety_signal=True, safety_notice_id="erfundene_id"), signals
    )
    assert decision.disposition == SafetyDisposition.safe_fallback


def test_safety_signal_from_llm_only_still_triggers():
    """Safety-Signal nur vom LLM (kein harter Regel-Trigger) zählt ebenfalls."""
    signals = DeterministicSignals(
        topic_in_allowed_scope=True,
        approved_safety_notice_ids=frozenset({"krisennotruf_de"}),
    )
    decision = decide_scope_safety(
        _classification(safety_signal=True, safety_notice_id="krisennotruf_de"), signals
    )
    assert decision.disposition == SafetyDisposition.safety_notice


def test_medical_advice_is_out_of_scope():
    decision = decide_scope_safety(
        _classification(requires_diagnosis_triage_treatment=True), IN_SCOPE_SIGNALS
    )
    assert decision.disposition == SafetyDisposition.out_of_scope
    assert "diagnosis" in decision.reason


def test_individual_eligibility_is_out_of_scope():
    decision = decide_scope_safety(
        _classification(requires_individual_eligibility_decision=True), IN_SCOPE_SIGNALS
    )
    assert decision.disposition == SafetyDisposition.out_of_scope


def test_low_confidence_falls_back():
    decision = decide_scope_safety(
        _classification(confidence=0.3),
        DeterministicSignals(topic_in_allowed_scope=True, confidence_floor=0.5),
    )
    assert decision.disposition == SafetyDisposition.safe_fallback


def test_safety_precedes_scope_rule():
    """Safety-Signal hat Vorrang vor der Scope-Regel (Reihenfolge fail-closed)."""
    signals = DeterministicSignals(
        topic_in_allowed_scope=False,  # Regel würde out_of_scope sagen
        hard_safety_trigger=True,
        approved_safety_notice_ids=frozenset({"krisennotruf_de"}),
    )
    decision = decide_scope_safety(
        _classification(safety_notice_id="krisennotruf_de"), signals
    )
    assert decision.disposition == SafetyDisposition.safety_notice
