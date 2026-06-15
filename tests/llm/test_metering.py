"""
Unit-Tests für Token-/Kosten-/Latenz-Metering (L3-2 / L4-3 / Spec §6).

Offline — kein LLM, kein DB. Prüft:
- LLMCallAudit trägt Metering-Felder korrekt.
- _compile_audit aggregiert Werte über mehrere Aufrufe.
- None-Felder (FakeLLMClient-Pfad) ergeben None im Audit.
- _compute_cost berechnet korrekt nach Preistabelle.
- FakeLLMClient gibt weiterhin None für alle Metering-Felder zurück.
"""

import uuid
from datetime import datetime, timezone

import pytest

from careapp.llm.anthropic_adapter import _compute_cost
from careapp.llm.port import LLMCallAudit, LLMTouchpoint, FakeLLMClient, LLMRequest, LLMCallBudget
from careapp.llm.channels import ThreeChannelPrompt
from careapp.llm.schemas import ScopeSafetyClassification
from careapp.orchestration.nodes import _compile_audit
from careapp.orchestration.state import (
    AuthContext, ConsultationState, GraphConfig, SessionBudgets,
)


# ------------------------------------------------------------------ #
# Preisberechnung                                                     #
# ------------------------------------------------------------------ #

def test_compute_cost_haiku():
    # 1000 Input + 500 Output @ $1/$5 pro Million
    cost = _compute_cost("claude-haiku-4-5", 1_000, 500)
    assert cost == pytest.approx((1_000 * 1.0 + 500 * 5.0) / 1_000_000)


def test_compute_cost_sonnet():
    cost = _compute_cost("claude-sonnet-4-6", 2_000, 300)
    assert cost == pytest.approx((2_000 * 3.0 + 300 * 15.0) / 1_000_000)


def test_compute_cost_unknown_model_returns_none():
    assert _compute_cost("some-unknown-model", 1000, 500) is None


# ------------------------------------------------------------------ #
# LLMCallAudit — Felder vorhanden und Optional                        #
# ------------------------------------------------------------------ #

def test_llm_call_audit_defaults_none():
    audit = LLMCallAudit(
        touchpoint=LLMTouchpoint.scope_safety,
        prompt_version="v1",
        model_id="claude-haiku-4-5",
    )
    assert audit.input_tokens is None
    assert audit.output_tokens is None
    assert audit.latency_ms is None
    assert audit.cost_usd is None


def test_llm_call_audit_with_metering():
    audit = LLMCallAudit(
        touchpoint=LLMTouchpoint.compose,
        prompt_version="v1",
        model_id="claude-sonnet-4-6",
        input_tokens=1500,
        output_tokens=300,
        latency_ms=820,
        cost_usd=0.000009,
    )
    assert audit.input_tokens == 1500
    assert audit.output_tokens == 300
    assert audit.latency_ms == 820


# ------------------------------------------------------------------ #
# FakeLLMClient — gibt None für Metering zurück                       #
# ------------------------------------------------------------------ #

def test_fake_llm_client_metering_fields_none():
    from careapp.llm.schemas import ScopeSafetyClassification
    fake = FakeLLMClient(responses={
        LLMTouchpoint.scope_safety: ScopeSafetyClassification(
            in_scope=True, requires_diagnosis_triage_treatment=False,
            requires_individual_eligibility_decision=False,
            safety_signal=False, prompt_injection_suspected=False,
            confidence=0.9, safety_notice_id=None,
        )
    })
    req = LLMRequest(
        prompt=ThreeChannelPrompt(system_rules="rules", task="task", user_input="hi"),
        response_schema=ScopeSafetyClassification,  # type: ignore[arg-type]
        audit=LLMCallAudit(
            touchpoint=LLMTouchpoint.scope_safety,
            prompt_version="v1",
            model_id="claude-haiku-4-5",
        ),
        budget=LLMCallBudget(max_input_tokens=1000, max_output_tokens=500, timeout_seconds=10.0),
    )
    result = fake.complete_structured(req)
    assert result.ok
    assert result.audit.input_tokens is None
    assert result.audit.output_tokens is None
    assert result.audit.latency_ms is None
    assert result.audit.cost_usd is None


# ------------------------------------------------------------------ #
# _compile_audit — Aggregation                                        #
# ------------------------------------------------------------------ #

def _make_state() -> ConsultationState:
    return ConsultationState(
        session_id=uuid.uuid4(),
        requested_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        auth=AuthContext(
            tenant_id=None, region_id=None,
            target_group_codes=(), consent_granted=True,
        ),
        budgets=SessionBudgets(),
    )


def _audit(tp: LLMTouchpoint, inp: int | None, out: int | None,
           lat: int | None, cost: float | None) -> LLMCallAudit:
    return LLMCallAudit(
        touchpoint=tp, prompt_version="v1", model_id="claude-haiku-4-5",
        input_tokens=inp, output_tokens=out, latency_ms=lat, cost_usd=cost,
    )


def test_compile_audit_aggregates_metering():
    state = _make_state()
    state.llm_audits = [
        _audit(LLMTouchpoint.scope_safety, 500, 100, 300, 0.0000006),
        _audit(LLMTouchpoint.intent,       800, 200, 450, 0.0000014),
        _audit(LLMTouchpoint.compose,     2000, 400, 900, 0.0000510),
    ]
    cfg = GraphConfig()
    result = _compile_audit(state, cfg)
    assert result.total_input_tokens == 500 + 800 + 2000
    assert result.total_output_tokens == 100 + 200 + 400
    assert result.total_latency_ms == 300 + 450 + 900
    assert result.total_cost_usd == pytest.approx(0.0000006 + 0.0000014 + 0.0000510)


def test_compile_audit_none_when_all_fields_none():
    """FakeLLMClient-Pfad: alle Metering-Felder None → Aggregat bleibt None."""
    state = _make_state()
    state.llm_audits = [
        _audit(LLMTouchpoint.scope_safety, None, None, None, None),
        _audit(LLMTouchpoint.intent, None, None, None, None),
    ]
    cfg = GraphConfig()
    result = _compile_audit(state, cfg)
    assert result.total_input_tokens is None
    assert result.total_output_tokens is None
    assert result.total_latency_ms is None
    assert result.total_cost_usd is None


def test_compile_audit_partial_metering():
    """Nur Teile haben Metering-Daten — nur diese werden summiert."""
    state = _make_state()
    state.llm_audits = [
        _audit(LLMTouchpoint.scope_safety, 400, 80, 200, 0.0000005),
        _audit(LLMTouchpoint.intent, None, None, None, None),  # FakeLLMClient
    ]
    cfg = GraphConfig()
    result = _compile_audit(state, cfg)
    assert result.total_input_tokens == 400
    assert result.total_output_tokens == 80
    assert result.total_latency_ms == 200
    assert result.total_cost_usd == pytest.approx(0.0000005)


def test_compile_audit_no_llm_calls():
    state = _make_state()
    state.llm_audits = []
    cfg = GraphConfig()
    result = _compile_audit(state, cfg)
    assert result.total_input_tokens is None
    assert result.total_cost_usd is None
