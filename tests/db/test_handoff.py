"""
Tests für HumanHandoff-Pfad (Layer 4, Welle 3 / L4-1).

Geprüft werden:
- HandoffQ → HumanHandoff wenn `handoff_available=True`
- HandoffQ → NoVerifiedInformation wenn `handoff_available=False` (Pilot-Default)
- Auslöser: Clarify-Budget erschöpft (max_clarify_rounds_exceeded)
- Auslöser: Coverage insufficient (coverage_insufficient)
- Handoff-Text: Default vs. konfigurierter Text
- Tool-Allowlist: HumanHandoff darf nur `handoff_write` nutzen

Alle Tests laufen mit FakeLLMClient gegen echte Supabase.
"""

import pytest

from careapp.llm.port import FakeLLMClient, LLMTouchpoint
from careapp.llm.schemas import IntentNextAction, IntentUnderstanding, ScopeSafetyClassification
from careapp.orchestration.graph import new_state, run_consultation
from careapp.orchestration.nodes import HANDOFF, HANDOFF_Q, NODE_ALLOWLIST
from careapp.orchestration.state import (
    AuthContext,
    Disposition,
    GraphConfig,
    ScopePolicy,
    SessionBudgets,
)
from careapp.orchestration.tools import Tool, ToolContext, ToolNotAllowed

from tests.db.test_layer2 import _TRUNCATE_ALL, T_PRESENT

AUTH_OK = AuthContext(
    tenant_id=None,
    region_id="NW-KREIS-NEUSS",
    target_group_codes=("relative",),
    consent_granted=True,
    locale="de",
)


@pytest.fixture
async def db_clean(session):
    await session.execute(_TRUNCATE_ALL)
    await session.commit()
    yield session
    await session.execute(_TRUNCATE_ALL)
    await session.commit()


def _cls(**overrides) -> ScopeSafetyClassification:
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


def _intent(*, missing=()) -> IntentUnderstanding:
    return IntentUnderstanding(
        intent_hypotheses=("heimunterbringung",),
        life_situation_hypotheses=(),
        confirmed_facts=(),
        missing_information=missing,
        medical_advice_requested=False,
        recommended_next_action=(
            IntentNextAction.ask_clarifying_question
            if missing
            else IntentNextAction.proceed_to_retrieval
        ),
    )


def _start(message="Meine Mutter muss ins Heim", **kw):
    return new_state(auth=AUTH_OK, latest_user_message=message, requested_at=T_PRESENT, **kw)


def _config_with_handoff(text: str | None = None) -> GraphConfig:
    return GraphConfig(policy=ScopePolicy(handoff_available=True, handoff_text=text))


# ------------------------------------------------------------------ #
# HandoffQ — Routing-Entscheidung                                     #
# ------------------------------------------------------------------ #


async def test_handoff_q_routes_to_no_verified_when_unavailable(db_clean):
    """Pilot-Default: handoff_available=False → HandoffQ → NoVerifiedInformation."""
    fake = FakeLLMClient(
        responses={
            LLMTouchpoint.scope_safety: _cls(),
            LLMTouchpoint.intent: _intent(),
        }
    )
    # Kein Beleg im DB → coverage_insufficient → HandoffQ → NoVerified
    state = await run_consultation(_start(), session=db_clean, llm=fake)

    assert state.disposition == Disposition.no_verified_information
    assert HANDOFF_Q in state.audit.nodes_traversed
    assert HANDOFF not in state.audit.nodes_traversed
    assert state.fallback_reason == "coverage_insufficient"


async def test_handoff_q_routes_to_handoff_when_available(db_clean):
    """handoff_available=True → HandoffQ → HumanHandoff → human_handoff disposition."""
    fake = FakeLLMClient(
        responses={
            LLMTouchpoint.scope_safety: _cls(),
            LLMTouchpoint.intent: _intent(),
        }
    )
    cfg = _config_with_handoff()
    state = await run_consultation(_start(), session=db_clean, llm=fake, config=cfg)

    assert state.disposition == Disposition.human_handoff
    assert HANDOFF_Q in state.audit.nodes_traversed
    assert HANDOFF in state.audit.nodes_traversed
    assert state.fallback_reason == "coverage_insufficient"


# ------------------------------------------------------------------ #
# Auslöser: Clarify-Budget erschöpft                                  #
# ------------------------------------------------------------------ #


async def test_clarify_budget_exhausted_routes_through_handoff_q(db_clean):
    """max_clarify_rounds=0 + handoff_available=True → Clarify → HandoffQ → HumanHandoff."""
    fake = FakeLLMClient(
        responses={
            LLMTouchpoint.scope_safety: _cls(),
            LLMTouchpoint.intent: _intent(missing=("region",)),
        }
    )
    cfg = _config_with_handoff()
    state = _start(budgets=SessionBudgets(max_clarify_rounds=0))
    state = await run_consultation(state, session=db_clean, llm=fake, config=cfg)

    assert state.disposition == Disposition.human_handoff
    assert HANDOFF_Q in state.audit.nodes_traversed
    assert HANDOFF in state.audit.nodes_traversed
    assert state.fallback_reason == "max_clarify_rounds_exceeded"


async def test_clarify_budget_exhausted_no_handoff_yields_no_verified(db_clean):
    """max_clarify_rounds=0 + handoff_available=False → NoVerifiedInformation (Regression)."""
    fake = FakeLLMClient(
        responses={
            LLMTouchpoint.scope_safety: _cls(),
            LLMTouchpoint.intent: _intent(missing=("region",)),
        }
    )
    state = _start(budgets=SessionBudgets(max_clarify_rounds=0))
    state = await run_consultation(state, session=db_clean, llm=fake)

    assert state.disposition == Disposition.no_verified_information
    assert state.fallback_reason == "max_clarify_rounds_exceeded"


# ------------------------------------------------------------------ #
# Handoff-Text                                                        #
# ------------------------------------------------------------------ #


async def test_handoff_uses_configured_text(db_clean):
    """Konfigurierter `handoff_text` erscheint im final_response."""
    custom_text = "Bitte wenden Sie sich an unsere Beratungsstelle unter 0800-CAREAPP."
    fake = FakeLLMClient(
        responses={
            LLMTouchpoint.scope_safety: _cls(),
            LLMTouchpoint.intent: _intent(),
        }
    )
    cfg = _config_with_handoff(text=custom_text)
    state = await run_consultation(_start(), session=db_clean, llm=fake, config=cfg)

    assert state.disposition == Disposition.human_handoff
    assert state.final_response is not None
    texts = [b.text for b in state.final_response.blocks if hasattr(b, "text")]
    assert any(custom_text in t for t in texts)


async def test_handoff_uses_default_text_when_none_configured(db_clean):
    """Kein `handoff_text` in Policy → Default-Text wird gesetzt (nicht leer)."""
    fake = FakeLLMClient(
        responses={
            LLMTouchpoint.scope_safety: _cls(),
            LLMTouchpoint.intent: _intent(),
        }
    )
    cfg = _config_with_handoff(text=None)
    state = await run_consultation(_start(), session=db_clean, llm=fake, config=cfg)

    assert state.disposition == Disposition.human_handoff
    assert state.final_response is not None
    texts = [b.text for b in state.final_response.blocks if hasattr(b, "text")]
    assert any(len(t) > 0 for t in texts)


# ------------------------------------------------------------------ #
# Tool-Allowlist (§3)                                                 #
# ------------------------------------------------------------------ #


def test_handoff_node_allowlist_contains_only_handoff_write():
    """HumanHandoff darf ausschließlich handoff_write nutzen (keine DB, kein LLM)."""
    assert NODE_ALLOWLIST[HANDOFF] == frozenset({Tool.handoff_write})
    assert Tool.db_read not in NODE_ALLOWLIST[HANDOFF]
    assert Tool.llm not in NODE_ALLOWLIST[HANDOFF]


def test_handoff_q_node_has_empty_allowlist():
    """HandoffQ ist rein deterministisch — kein Tool erlaubt."""
    assert NODE_ALLOWLIST[HANDOFF_Q] == frozenset()


def test_handoff_tool_not_allowed_in_safety_node():
    """SafetyCheck darf den Übergabe-Prozess strukturell nicht aufrufen."""
    from careapp.orchestration.nodes import SAFETY
    ctx = ToolContext(SAFETY, NODE_ALLOWLIST[SAFETY], None, None)
    with pytest.raises(ToolNotAllowed):
        ctx.handoff()
