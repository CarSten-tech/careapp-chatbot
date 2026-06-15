"""
Tests für L4-4: Rate Limiting + Input-Größenlimit.

Prüft die beiden Guard-Checks in `session_start`:
  1. Input-Größenlimit: len(latest_user_message) > max_user_message_chars → NO_VERIFIED
  2. Per-Session-Rate-Limit: turns_this_session >= max_turns_per_session → NO_VERIFIED

Außerdem: extract_checkpoint erhöht turns_this_session um 1 (Inkrementierung),
und der Checkpoint-Roundtrip persistiert turns_this_session korrekt.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from careapp.llm.port import FakeLLMClient, LLMTouchpoint
from careapp.llm.schemas import ScopeSafetyClassification
from careapp.orchestration.checkpoint import (
    InMemoryCheckpointStore,
    SupabaseCheckpointStore,
    extract_checkpoint,
)
from careapp.orchestration.graph import new_state, run_consultation
from careapp.orchestration.state import (
    AuthContext,
    Disposition,
    GraphConfig,
    SessionBudgets,
)

from tests.db.test_layer2 import T_PRESENT, _TRUNCATE_ALL

# ------------------------------------------------------------------ #
# Fixtures                                                             #
# ------------------------------------------------------------------ #

AUTH_OK = AuthContext(
    tenant_id=None,
    region_id="NW-KREIS-NEUSS",
    target_group_codes=("relative",),
    consent_granted=True,
    locale="de",
)

_CFG = GraphConfig()  # Default-Versionen für Checkpoint-Roundtrip-Tests

_FAKE_SCOPE_OK = FakeLLMClient(responses={
    LLMTouchpoint.scope_safety: ScopeSafetyClassification(
        in_scope=True,
        requires_diagnosis_triage_treatment=False,
        requires_individual_eligibility_decision=False,
        safety_signal=False,
        prompt_injection_suspected=False,
        confidence=0.9,
        safety_notice_id=None,
    ),
})


@pytest.fixture
async def db_clean(session):
    await session.execute(_TRUNCATE_ALL)
    await session.commit()
    yield session
    await session.execute(_TRUNCATE_ALL)
    await session.commit()


def _state(message="Heimunterbringung", **kw):
    return new_state(auth=AUTH_OK, latest_user_message=message, requested_at=T_PRESENT, **kw)


# ------------------------------------------------------------------ #
# Input-Größenlimit                                                    #
# ------------------------------------------------------------------ #


async def test_message_at_limit_passes(db_clean):
    """len == max_user_message_chars → erlaubt (Grenzfall, Zeichen-exakt)."""
    budgets = SessionBudgets(max_user_message_chars=20)
    state = _state("x" * 20, budgets=budgets)  # genau 20 Zeichen = erlaubt
    state_out = await run_consultation(state, session=db_clean, llm=_FAKE_SCOPE_OK)
    # Intent-Fehler → no_verified (kein echter Intent-Client) — aber NICHT wegen Input-Limit
    assert state_out.fallback_reason is None or "input_too_large" not in (state_out.fallback_reason or "")


async def test_message_one_over_limit__yields_no_verified(db_clean):
    """len == max + 1 → no_verified_information (L4-4 Guard)."""
    budgets = SessionBudgets(max_user_message_chars=20)
    state = _state("x" * 21, budgets=budgets)  # 21 Zeichen > 20 → blockiert
    state_out = await run_consultation(state, session=db_clean, llm=_FAKE_SCOPE_OK)
    assert state_out.disposition == Disposition.no_verified_information
    assert state_out.fallback_reason is not None
    assert "input_too_large" in state_out.fallback_reason


async def test_large_message__yields_no_verified(db_clean):
    """Sehr langer Input (10.000 Zeichen) → no_verified_information."""
    state = _state("A" * 10_000)  # default max = 2000
    state_out = await run_consultation(state, session=db_clean, llm=_FAKE_SCOPE_OK)
    assert state_out.disposition == Disposition.no_verified_information
    assert "input_too_large" in (state_out.fallback_reason or "")


async def test_input_limit_respected_at_boundary(db_clean):
    """Default-Grenze (2000 Zeichen) exakt — erlaubt."""
    state = _state("B" * 2000)
    state_out = await run_consultation(state, session=db_clean, llm=_FAKE_SCOPE_OK)
    assert "input_too_large" not in (state_out.fallback_reason or "")


# ------------------------------------------------------------------ #
# Per-Session-Rate-Limit                                              #
# ------------------------------------------------------------------ #


async def test_turn_within_limit_passes(db_clean):
    """turns_this_session = 0, max = 5 → nicht geblockt."""
    budgets = SessionBudgets(max_turns_per_session=5)
    state = _state(turns_this_session=0, budgets=budgets)
    state_out = await run_consultation(state, session=db_clean, llm=_FAKE_SCOPE_OK)
    assert "rate_limit_exceeded" not in (state_out.fallback_reason or "")


async def test_turn_at_limit__yields_no_verified(db_clean):
    """turns_this_session == max_turns_per_session → geblockt (≥ ist die Bedingung)."""
    budgets = SessionBudgets(max_turns_per_session=5)
    state = _state(turns_this_session=5, budgets=budgets)
    state_out = await run_consultation(state, session=db_clean, llm=_FAKE_SCOPE_OK)
    assert state_out.disposition == Disposition.no_verified_information
    assert "rate_limit_exceeded" in (state_out.fallback_reason or "")


async def test_turn_over_limit__yields_no_verified(db_clean):
    """turns_this_session > max_turns_per_session → ebenfalls geblockt."""
    budgets = SessionBudgets(max_turns_per_session=3)
    state = _state(turns_this_session=99, budgets=budgets)
    state_out = await run_consultation(state, session=db_clean, llm=_FAKE_SCOPE_OK)
    assert state_out.disposition == Disposition.no_verified_information
    assert "rate_limit_exceeded" in (state_out.fallback_reason or "")


async def test_turn_just_before_limit_passes(db_clean):
    """turns_this_session = max - 1 → noch erlaubt."""
    budgets = SessionBudgets(max_turns_per_session=5)
    state = _state(turns_this_session=4, budgets=budgets)  # max=5, turns=4 → erlaubt
    state_out = await run_consultation(state, session=db_clean, llm=_FAKE_SCOPE_OK)
    assert "rate_limit_exceeded" not in (state_out.fallback_reason or "")


# ------------------------------------------------------------------ #
# extract_checkpoint — Inkrementierung                                 #
# ------------------------------------------------------------------ #


async def test_extract_checkpoint_increments_turns(db_clean):
    """extract_checkpoint erhöht turns_this_session um genau 1."""
    budgets = SessionBudgets(max_turns_per_session=10)
    state = _state(turns_this_session=3, budgets=budgets)
    cfg = _CFG
    state_out = await run_consultation(state, session=db_clean, llm=_FAKE_SCOPE_OK)
    cp = extract_checkpoint(state_out, cfg)
    assert cp.turns_this_session == 4  # 3 + 1


async def test_extract_checkpoint_first_turn_yields_one(db_clean):
    """Erster Turn (turns=0) → Checkpoint enthält turns_this_session=1."""
    state = _state(turns_this_session=0)
    cfg = _CFG
    state_out = await run_consultation(state, session=db_clean, llm=_FAKE_SCOPE_OK)
    cp = extract_checkpoint(state_out, cfg)
    assert cp.turns_this_session == 1


# ------------------------------------------------------------------ #
# InMemoryCheckpointStore — Roundtrip                                  #
# ------------------------------------------------------------------ #


async def test_inmemory_roundtrip_turns(db_clean):
    """InMemoryCheckpointStore persistiert turns_this_session korrekt."""
    store = InMemoryCheckpointStore()
    cfg = _CFG

    # Turn 1
    state1 = _state(turns_this_session=0)
    out1 = await run_consultation(state1, session=db_clean, llm=_FAKE_SCOPE_OK)
    cp1 = extract_checkpoint(out1, cfg)
    await store.save(cp1)
    assert cp1.turns_this_session == 1

    # Turn 2: aus Checkpoint laden
    loaded = await store.load(cp1.session_id)
    assert loaded is not None
    assert loaded.turns_this_session == 1

    state2 = new_state(
        auth=AUTH_OK, latest_user_message="Nächste Frage?", requested_at=T_PRESENT,
        session_id=loaded.session_id,
        turns_this_session=loaded.turns_this_session,
        budgets=loaded.budgets,
    )
    out2 = await run_consultation(state2, session=db_clean, llm=_FAKE_SCOPE_OK)
    cp2 = extract_checkpoint(out2, cfg)
    await store.save(cp2)
    assert cp2.turns_this_session == 2


# ------------------------------------------------------------------ #
# SupabaseCheckpointStore — DB-Roundtrip                              #
# ------------------------------------------------------------------ #


async def test_supabase_roundtrip_turns(db_clean):
    """SupabaseCheckpointStore persistiert turns_this_session und max-Werte korrekt."""
    store = SupabaseCheckpointStore(db_clean)
    cfg = _CFG

    state = _state(turns_this_session=4, budgets=SessionBudgets(max_turns_per_session=7))
    out = await run_consultation(state, session=db_clean, llm=_FAKE_SCOPE_OK)
    cp = extract_checkpoint(out, cfg)
    assert cp.turns_this_session == 5

    await store.save(cp)
    loaded = await store.load(cp.session_id)

    assert loaded is not None
    assert loaded.turns_this_session == 5
    assert loaded.budgets.max_turns_per_session == 7
    assert loaded.budgets.max_user_message_chars == 2000  # Default


async def test_supabase_turns_upsert(db_clean):
    """UPSERT aktualisiert turns_this_session bei erneutem Speichern korrekt."""
    store = SupabaseCheckpointStore(db_clean)
    cfg = _CFG

    state = _state(turns_this_session=2)
    out = await run_consultation(state, session=db_clean, llm=_FAKE_SCOPE_OK)
    cp1 = extract_checkpoint(out, cfg)  # turns = 3
    await store.save(cp1)

    # Zweiter Speichervorgang desselben Checkpoints (z.B. Retry) — Turns müssen konsistent sein
    state2 = new_state(
        auth=AUTH_OK, latest_user_message="Und weiter?", requested_at=T_PRESENT,
        session_id=cp1.session_id, turns_this_session=cp1.turns_this_session,
    )
    out2 = await run_consultation(state2, session=db_clean, llm=_FAKE_SCOPE_OK)
    cp2 = extract_checkpoint(out2, cfg)  # turns = 4
    await store.save(cp2)

    loaded = await store.load(cp1.session_id)
    assert loaded is not None
    assert loaded.turns_this_session == 4
