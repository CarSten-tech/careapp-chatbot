"""
Integrationstests für die Conversation-Orchestrierung (Layer 4.1).

End-to-End durch den statischen Graphen mit `FakeLLMClient` (kein Live-LLM) gegen
die echte Supabase-Instanz. Geprüft werden: Happy Path, die Fail-Closed-Kanten der
Degradationsmatrix (§7), Budget-Grenzen (§4) und die Tool-Allowlist (§3).
"""

import uuid

import pytest

from careapp.llm.port import FakeLLMClient, LLMTouchpoint
from careapp.llm.schemas import (
    ClarifyingQuestion,
    ComposerResponse,
    FactualStatementBlock,
    IntentNextAction,
    IntentUnderstanding,
    ScopeSafetyClassification,
)
from careapp.orchestration.graph import new_state, run_consultation
from careapp.orchestration.nodes import SAFETY, NODE_ALLOWLIST
from careapp.orchestration.state import AuthContext, Disposition, SessionBudgets
from careapp.orchestration.tools import Tool, ToolContext, ToolNotAllowed

from tests.db.test_composer import _seed_one_cv
from tests.db.test_layer2 import _TRUNCATE_ALL, T_PRESENT

# Auth-Kontext, der zu BASE_CTX passt (Region Neuss, Angehörige, Consent erteilt).
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


# ------------------------------------------------------------------ #
# Canned LLM-Antworten je Touchpoint                                  #
# ------------------------------------------------------------------ #


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


def _clarify_q() -> ClarifyingQuestion:
    return ClarifyingQuestion(
        question_text="In welchem Kreis wohnt die betroffene Person?",
        addresses_missing_keys=("region",),
        options=(),
    )


def _start(message="Meine Mutter muss ins Heim", **kw):
    return new_state(auth=AUTH_OK, latest_user_message=message, requested_at=T_PRESENT, **kw)


# ------------------------------------------------------------------ #
# Happy Path                                                          #
# ------------------------------------------------------------------ #


async def test_happy_path_presents_grounded_answer(db_clean):
    cv, _pkg = await _seed_one_cv(db_clean)
    fake = FakeLLMClient(
        responses={
            LLMTouchpoint.scope_safety: _cls(),
            LLMTouchpoint.intent: _intent(),
            LLMTouchpoint.compose: ComposerResponse(
                blocks=(
                    FactualStatementBlock(
                        text="Es besteht ein Anspruch auf vollstationäre Pflege.",
                        claim_version_ids=(cv.id,),
                    ),
                )
            ),
        }
    )

    state = await run_consultation(_start(), session=db_clean, llm=fake)

    assert state.disposition == Disposition.presented
    assert state.audit is not None and state.audit.validation_passed is True
    assert str(cv.id) in state.audit.evidence_claim_version_ids
    types = [b.type for b in state.final_response.blocks]
    assert "factual_statement" in types
    # Audit referenziert die durchlaufenen Nodes, Tool-Aufrufe und Versions-Tripel.
    assert "ComposeAnswer" in state.audit.nodes_traversed
    assert "PresentAnswer" in state.audit.nodes_traversed
    assert "SafetyCheck:llm" in state.audit.tool_calls
    assert "ComposeAnswer:db_read" in state.audit.tool_calls
    assert state.audit.versions.graph_version == "graph-v1"
    assert len(state.audit.llm_calls) == 3  # scope, intent, compose


# ------------------------------------------------------------------ #
# Scope/Safety-Kanten                                                 #
# ------------------------------------------------------------------ #


async def test_out_of_scope_short_circuits_to_safe_scope(db_clean):
    """LLM hält out of scope → SafeScopeResponse, ohne den Wissensbestand zu berühren."""
    fake = FakeLLMClient(responses={LLMTouchpoint.scope_safety: _cls(in_scope=False)})
    state = await run_consultation(_start(), session=db_clean, llm=fake)

    assert state.disposition == Disposition.safe_scope_response
    assert "UnderstandConcern" not in state.audit.nodes_traversed
    assert "ComposeAnswer" not in state.audit.nodes_traversed


async def test_safety_parse_error_falls_back_to_safe_scope(db_clean):
    """Parsefehler bei LLM-1 → konservativ (SafeScopeResponse), §7."""
    fake = FakeLLMClient(fail_touchpoints=frozenset({LLMTouchpoint.scope_safety}))
    state = await run_consultation(_start(), session=db_clean, llm=fake)

    assert state.disposition == Disposition.safe_scope_response


async def test_missing_consent_short_circuits(db_clean):
    """Fehlende Einwilligung → SafeScopeResponse vor jedem LLM-Aufruf."""
    auth = AuthContext(
        tenant_id=None,
        region_id="NW-KREIS-NEUSS",
        target_group_codes=("relative",),
        consent_granted=False,
    )
    state = new_state(auth=auth, latest_user_message="Hallo", requested_at=T_PRESENT)
    state = await run_consultation(state, session=db_clean, llm=FakeLLMClient())

    assert state.disposition == Disposition.safe_scope_response
    assert state.audit.nodes_traversed == (
        "SessionStart",
        "ConsentAndAccessCheck",
        "SafeScopeResponse",
    )
    assert state.audit.llm_calls == ()  # kein LLM-Aufruf


# ------------------------------------------------------------------ #
# Fail-Closed entlang des Evidenz-/Composer-Pfads                     #
# ------------------------------------------------------------------ #


async def test_coverage_insufficient_yields_no_verified(db_clean):
    """Keine eligible Evidenz → insufficient → NoVerifiedInformation."""
    fake = FakeLLMClient(
        responses={LLMTouchpoint.scope_safety: _cls(), LLMTouchpoint.intent: _intent()}
    )
    state = await run_consultation(_start(), session=db_clean, llm=fake)

    assert state.disposition == Disposition.no_verified_information
    assert state.fallback_reason == "coverage_insufficient"
    assert "ComposeAnswer" not in state.audit.nodes_traversed


async def test_composer_invented_cv_yields_no_verified(db_clean):
    """Composer erfindet eine claim_version_id → Validator scheitert → NoVerified (D8, §7)."""
    await _seed_one_cv(db_clean)
    fake = FakeLLMClient(
        responses={
            LLMTouchpoint.scope_safety: _cls(),
            LLMTouchpoint.intent: _intent(),
            LLMTouchpoint.compose: ComposerResponse(
                blocks=(
                    FactualStatementBlock(text="Erfunden.", claim_version_ids=(uuid.uuid4(),)),
                )
            ),
        }
    )
    state = await run_consultation(_start(), session=db_clean, llm=fake)

    assert state.disposition == Disposition.no_verified_information
    assert state.fallback_reason == "validation_failed"
    assert state.audit.validation_passed is False


# ------------------------------------------------------------------ #
# Clarify + Budgets (§4)                                              #
# ------------------------------------------------------------------ #


async def test_missing_information_routes_to_clarify(db_clean):
    fake = FakeLLMClient(
        responses={
            LLMTouchpoint.scope_safety: _cls(),
            LLMTouchpoint.intent: _intent(missing=("region",)),
            LLMTouchpoint.clarify: _clarify_q(),
        }
    )
    state = await run_consultation(_start(), session=db_clean, llm=fake)

    assert state.disposition == Disposition.clarify
    assert state.final_response.blocks[0].type == "clarifying_question"
    assert state.clarify_rounds_used == 1


async def test_clarify_budget_exhausted_yields_no_verified(db_clean):
    """max_clarify_rounds erreicht → HandoffQ → (Pilot) NoVerifiedInformation."""
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
# Tool-Allowlist (§3) — serverseitig erzwungen                        #
# ------------------------------------------------------------------ #


def test_tool_allowlist_blocks_db_read_in_safety_node():
    """SafetyCheck darf den Wissensbestand strukturell nicht abfragen."""
    assert Tool.db_read not in NODE_ALLOWLIST[SAFETY]
    ctx = ToolContext(SAFETY, NODE_ALLOWLIST[SAFETY], None, None)
    with pytest.raises(ToolNotAllowed):
        ctx.db()
    # llm ist erlaubt → kein Fehler bei der Allowlist-Prüfung
    ctx.llm()
    assert Tool.llm in ctx.used
