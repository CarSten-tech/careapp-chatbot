"""
Tests für Checkpoint-Persistenz (Layer 4.4 / L4-2 / §5).

Geprüft werden:
- Roundtrip In-Memory und DB (save → load)
- UPSERT: zweiter save auf gleiche session_id aktualisiert
- Unbekannte session_id → None
- extract_checkpoint: korrekte Felder aus Turn-State
- PII-Schutz: SessionCheckpoint hat kein latest_user_message / auth-Feld
- Mehrturniger Fortschritt: clarify_rounds_used + pathway_answers akkumulieren

Alle DB-Tests laufen gegen echte Supabase, InMemory-Tests ohne DB.
"""

import dataclasses
import uuid
from datetime import timezone

import pytest
from sqlalchemy import text

from careapp.llm.port import FakeLLMClient, LLMTouchpoint
from careapp.llm.schemas import (
    ClarifyingQuestion,
    IntentNextAction,
    IntentUnderstanding,
    ScopeSafetyClassification,
)
from careapp.orchestration.checkpoint import (
    CheckpointStore,
    InMemoryCheckpointStore,
    SessionCheckpoint,
    SupabaseCheckpointStore,
    extract_checkpoint,
)
from careapp.orchestration.graph import new_state, run_consultation
from careapp.orchestration.state import (
    AuthContext,
    GraphConfig,
    GraphVersionTriple,
    SessionBudgets,
)

from tests.db.test_layer2 import _TRUNCATE_ALL, T_PRESENT

AUTH_OK = AuthContext(
    tenant_id=None,
    region_id="NW-KREIS-NEUSS",
    target_group_codes=("relative",),
    consent_granted=True,
    locale="de",
)

_TRUNCATE_CHECKPOINTS = text("TRUNCATE TABLE session_checkpoints")


@pytest.fixture
async def db_clean(session):
    await session.execute(_TRUNCATE_ALL)
    await session.execute(_TRUNCATE_CHECKPOINTS)
    await session.commit()
    yield session
    await session.execute(_TRUNCATE_ALL)
    await session.execute(_TRUNCATE_CHECKPOINTS)
    await session.commit()


def _make_checkpoint(**overrides) -> SessionCheckpoint:
    base = dict(
        session_id=uuid.uuid4(),
        clarify_rounds_used=0,
        pathway_answers={},
        budgets=SessionBudgets(),
        versions=GraphVersionTriple("graph-v1", "prompts-v1", "models-v1"),
    )
    base.update(overrides)
    return SessionCheckpoint(**base)


# ------------------------------------------------------------------ #
# Protocol-Konformität                                                #
# ------------------------------------------------------------------ #


def test_in_memory_store_satisfies_protocol():
    assert isinstance(InMemoryCheckpointStore(), CheckpointStore)


def test_supabase_store_satisfies_protocol(db_clean):
    assert isinstance(SupabaseCheckpointStore(db_clean), CheckpointStore)


# ------------------------------------------------------------------ #
# PII-Schutz (§5)                                                     #
# ------------------------------------------------------------------ #


def test_checkpoint_does_not_contain_pii_fields():
    """SessionCheckpoint darf strukturell keinen Freitext oder Auth-Kontext enthalten."""
    field_names = {f.name for f in dataclasses.fields(SessionCheckpoint)}
    assert "latest_user_message" not in field_names
    assert "auth" not in field_names
    assert "confirmed_facts" not in field_names
    assert "trace" not in field_names
    assert "llm_audits" not in field_names


# ------------------------------------------------------------------ #
# InMemoryCheckpointStore                                             #
# ------------------------------------------------------------------ #


async def test_in_memory_roundtrip():
    store = InMemoryCheckpointStore()
    cp = _make_checkpoint(clarify_rounds_used=2, pathway_answers={"pflegegrad": "true"})
    await store.save(cp)
    loaded = await store.load(cp.session_id)
    assert loaded is not None
    assert loaded.session_id == cp.session_id
    assert loaded.clarify_rounds_used == 2
    assert loaded.pathway_answers == {"pflegegrad": "true"}
    assert loaded.budgets == cp.budgets
    assert loaded.versions == cp.versions


async def test_in_memory_unknown_session_returns_none():
    store = InMemoryCheckpointStore()
    assert await store.load(uuid.uuid4()) is None


async def test_in_memory_upsert_updates_existing():
    store = InMemoryCheckpointStore()
    sid = uuid.uuid4()
    await store.save(_make_checkpoint(session_id=sid, clarify_rounds_used=0))
    await store.save(_make_checkpoint(session_id=sid, clarify_rounds_used=1,
                                      pathway_answers={"hat_pflegegrad": "false"}))
    loaded = await store.load(sid)
    assert loaded.clarify_rounds_used == 1
    assert loaded.pathway_answers == {"hat_pflegegrad": "false"}


async def test_in_memory_upsert_preserves_created_at():
    store = InMemoryCheckpointStore()
    cp = _make_checkpoint()
    await store.save(cp)
    original_created_at = (await store.load(cp.session_id)).created_at
    await store.save(_make_checkpoint(session_id=cp.session_id, clarify_rounds_used=1))
    updated = await store.load(cp.session_id)
    assert updated.created_at == original_created_at  # created_at bleibt stabil
    assert updated.updated_at >= original_created_at  # updated_at steigt


# ------------------------------------------------------------------ #
# SupabaseCheckpointStore (gegen echte Supabase)                      #
# ------------------------------------------------------------------ #


async def test_db_roundtrip(db_clean):
    store = SupabaseCheckpointStore(db_clean)
    cp = _make_checkpoint(
        clarify_rounds_used=1,
        pathway_answers={"stationaer": "ja"},
        budgets=SessionBudgets(max_clarify_rounds=3),
        versions=GraphVersionTriple("graph-v2", "prompts-v1", "models-v1"),
    )
    await store.save(cp)
    loaded = await store.load(cp.session_id)
    assert loaded is not None
    assert loaded.session_id == cp.session_id
    assert loaded.clarify_rounds_used == 1
    assert loaded.pathway_answers == {"stationaer": "ja"}
    assert loaded.budgets.max_clarify_rounds == 3
    assert loaded.versions.graph_version == "graph-v2"
    assert loaded.created_at.tzinfo is not None  # timezone-aware


async def test_db_unknown_session_returns_none(db_clean):
    store = SupabaseCheckpointStore(db_clean)
    assert await store.load(uuid.uuid4()) is None


async def test_db_upsert_updates_existing(db_clean):
    store = SupabaseCheckpointStore(db_clean)
    sid = uuid.uuid4()
    await store.save(_make_checkpoint(session_id=sid, clarify_rounds_used=0))
    await store.save(_make_checkpoint(session_id=sid, clarify_rounds_used=2,
                                      pathway_answers={"pflegegrad": "true"}))
    loaded = await store.load(sid)
    assert loaded.clarify_rounds_used == 2
    assert loaded.pathway_answers == {"pflegegrad": "true"}


# ------------------------------------------------------------------ #
# extract_checkpoint                                                   #
# ------------------------------------------------------------------ #


async def test_extract_checkpoint_captures_state(db_clean):
    """extract_checkpoint liest session_id, clarify_rounds_used, pathway_answers, versions."""
    fake = FakeLLMClient(
        responses={
            LLMTouchpoint.scope_safety: ScopeSafetyClassification(
                in_scope=True,
                requires_diagnosis_triage_treatment=False,
                requires_individual_eligibility_decision=False,
                safety_signal=False,
                prompt_injection_suspected=False,
                confidence=0.9,
                safety_notice_id=None,
            ),
            LLMTouchpoint.intent: IntentUnderstanding(
                intent_hypotheses=("heimunterbringung",),
                life_situation_hypotheses=(),
                confirmed_facts=(),
                missing_information=("region",),
                medical_advice_requested=False,
                recommended_next_action=IntentNextAction.ask_clarifying_question,
            ),
            LLMTouchpoint.clarify: ClarifyingQuestion(
                question_text="In welchem Kreis?",
                addresses_missing_keys=("region",),
                options=(),
            ),
        }
    )
    cfg = GraphConfig()
    state = new_state(auth=AUTH_OK, latest_user_message="Frage", requested_at=T_PRESENT)
    state = await run_consultation(state, session=db_clean, llm=fake, config=cfg)

    cp = extract_checkpoint(state, cfg)

    assert cp.session_id == state.session_id
    assert cp.clarify_rounds_used == state.clarify_rounds_used
    assert cp.pathway_answers == state.pathway_answers
    assert cp.versions == cfg.versions
    assert cp.budgets == state.budgets


# ------------------------------------------------------------------ #
# Mehrturniger Fortschritt (End-to-End mit InMemory-Store)            #
# ------------------------------------------------------------------ #


async def test_multiturn_clarify_rounds_persist(db_clean):
    """
    Zwei aufeinanderfolgende Turns mit checkpoint-basiertem Fortschritt.
    Turn 1 führt Clarify (round 1), speichert Checkpoint.
    Turn 2 lädt Checkpoint → clarify_rounds_used startet bei 1.
    """
    store = InMemoryCheckpointStore()
    cfg = GraphConfig()

    def _cls():
        return ScopeSafetyClassification(
            in_scope=True,
            requires_diagnosis_triage_treatment=False,
            requires_individual_eligibility_decision=False,
            safety_signal=False,
            prompt_injection_suspected=False,
            confidence=0.9,
            safety_notice_id=None,
        )

    def _intent_missing():
        return IntentUnderstanding(
            intent_hypotheses=("heimunterbringung",),
            life_situation_hypotheses=(),
            confirmed_facts=(),
            missing_information=("region",),
            medical_advice_requested=False,
            recommended_next_action=IntentNextAction.ask_clarifying_question,
        )

    fake = FakeLLMClient(
        responses={
            LLMTouchpoint.scope_safety: _cls(),
            LLMTouchpoint.intent: _intent_missing(),
            LLMTouchpoint.clarify: ClarifyingQuestion(
                question_text="Welcher Kreis?", addresses_missing_keys=("region",), options=()
            ),
        }
    )

    # Turn 1
    state1 = new_state(auth=AUTH_OK, latest_user_message="Meine Mutter muss ins Heim",
                       requested_at=T_PRESENT)
    state1 = await run_consultation(state1, session=db_clean, llm=fake, config=cfg)
    assert state1.clarify_rounds_used == 1

    cp = extract_checkpoint(state1, cfg)
    await store.save(cp)

    # Turn 2: Checkpoint laden und State wiederherstellen
    loaded = await store.load(state1.session_id)
    assert loaded is not None
    assert loaded.clarify_rounds_used == 1

    state2 = new_state(
        auth=AUTH_OK,
        latest_user_message="Kreis Neuss",
        requested_at=T_PRESENT,
        session_id=loaded.session_id,
        clarify_rounds_used=loaded.clarify_rounds_used,
        pathway_answers=loaded.pathway_answers,
        budgets=loaded.budgets,
    )
    # session_id bleibt identisch (gleiche Konversation)
    assert state2.session_id == state1.session_id
    assert state2.clarify_rounds_used == 1
