"""
Integrationstests für den Pathway-Pfad der Orchestrierung (Layer 4.2).

Mehrturniger, deterministischer Durchlauf der Pilot-Lebenslage „heimunterbringung"
gegen die echte Supabase-Instanz (FakeLLMClient, kein Live-LLM). Geprüft:
- `ResolvePathway` mappt resolved_intent → LifeSituation.code → published Pathway,
- `Clarify` liest den nächsten offenen `PathwayStep` (Template, kein freies Fragen),
- Antwort-Zweige (`PathwayBranch`) steuern den nächsten Schritt deterministisch,
- Pathway-Abschluss → `BuildRetrievalPlan` (topic_hint-Fokus) → Compose → Present.
"""

import uuid
from datetime import datetime, timezone

import pytest

from careapp.db.models.pathway import (
    DecisionNode,
    DecisionNodeInputType,
    LifeSituation,
    LifeSituationPathway,
    PathwayBranch,
    PathwayStatus,
    PathwayStep,
)
from careapp.llm.port import FakeLLMClient, LLMTouchpoint
from careapp.llm.schemas import ComposerResponse, FactualStatementBlock
from careapp.orchestration.graph import new_state, run_consultation
from careapp.orchestration.state import Disposition

from tests.db.test_layer2 import _TRUNCATE_ALL, T_PRESENT, _Builder
from tests.db.test_orchestration import AUTH_OK, _cls, _intent

Q_STEP1 = "Liegt die betroffene Person gerade im Krankenhaus?"
Q_STEP2 = "Hat die betroffene Person bereits einen anerkannten Pflegegrad?"


@pytest.fixture
async def db_clean(session):
    await session.execute(_TRUNCATE_ALL)
    await session.commit()
    yield session
    await session.execute(_TRUNCATE_ALL)
    await session.commit()


async def _seed_pathway(db):
    """
    Synthetischer published Pathway 'heimunterbringung' mit zwei Schritten:
      Step1 (krankenhaus_aktuell): "true" → Step2, "false" → Ende (scope-Modifier).
      Step2 (pflegegrad_vorhanden): beide Antworten → Ende.
    Plus eine eligible CV in stationaere_pflege (für die Coverage nach Abschluss).
    """
    b = _Builder()
    for obj in b.source_objects():
        db.add(obj)
    await db.commit()
    cv = await b.insert_full_cv(db)  # topic_scope=stationaere_pflege, published, eligible

    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    ls = LifeSituation(id=uuid.uuid4(), code="heimunterbringung", label_de="Heim", created_at=now)
    pathway = LifeSituationPathway(
        id=uuid.uuid4(),
        life_situation_id=ls.id,
        version=1,
        status=PathwayStatus.published,
        published_at=now,
        locale="de",
        description="SYNTHETISCH",
    )
    dn1 = DecisionNode(
        id=uuid.uuid4(),
        code="krankenhaus_aktuell",
        question_template_de=Q_STEP1,
        input_type=DecisionNodeInputType.boolean,
        options=None,
        created_at=now,
    )
    dn2 = DecisionNode(
        id=uuid.uuid4(),
        code="pflegegrad_vorhanden",
        question_template_de=Q_STEP2,
        input_type=DecisionNodeInputType.boolean,
        options=None,
        created_at=now,
    )
    db.add_all([ls, pathway, dn1, dn2])
    await db.commit()

    step1 = PathwayStep(
        id=uuid.uuid4(),
        pathway_id=pathway.id,
        step_order=1,
        decision_node_id=dn1.id,
        is_required=True,
        topic_hint="stationaere_pflege",
    )
    step2 = PathwayStep(
        id=uuid.uuid4(),
        pathway_id=pathway.id,
        step_order=2,
        decision_node_id=dn2.id,
        is_required=True,
        topic_hint="stationaere_pflege",
    )
    db.add_all([step1, step2])
    await db.commit()

    db.add_all(
        [
            PathwayBranch(
                id=uuid.uuid4(),
                pathway_step_id=step1.id,
                answer_value="true",
                next_step_id=step2.id,
                retrieval_scope_modifier=None,
            ),
            PathwayBranch(
                id=uuid.uuid4(),
                pathway_step_id=step1.id,
                answer_value="false",
                next_step_id=None,
                retrieval_scope_modifier={"topic_scope": "stationaere_pflege"},
            ),
            PathwayBranch(
                id=uuid.uuid4(),
                pathway_step_id=step2.id,
                answer_value="true",
                next_step_id=None,
                retrieval_scope_modifier=None,
            ),
            PathwayBranch(
                id=uuid.uuid4(),
                pathway_step_id=step2.id,
                answer_value="false",
                next_step_id=None,
                retrieval_scope_modifier=None,
            ),
        ]
    )
    await db.commit()
    return cv


def _fake_clarify_only() -> FakeLLMClient:
    return FakeLLMClient(
        responses={LLMTouchpoint.scope_safety: _cls(), LLMTouchpoint.intent: _intent()}
    )


def _fake_full(cv_id) -> FakeLLMClient:
    return FakeLLMClient(
        responses={
            LLMTouchpoint.scope_safety: _cls(),
            LLMTouchpoint.intent: _intent(),
            LLMTouchpoint.compose: ComposerResponse(
                blocks=(
                    FactualStatementBlock(
                        text="Anspruch auf vollstationäre Pflege.", claim_version_ids=(cv_id,)
                    ),
                )
            ),
        }
    )


def _turn(message, **kw):
    return new_state(auth=AUTH_OK, latest_user_message=message, requested_at=T_PRESENT, **kw)


# ------------------------------------------------------------------ #
# Pathway-Navigation                                                  #
# ------------------------------------------------------------------ #


async def test_turn1_asks_first_step_as_template(db_clean):
    """Turn 1: ResolvePathway findet den Pathway → Clarify stellt den ersten Step (Template)."""
    await _seed_pathway(db_clean)
    state = await run_consultation(
        _turn("Meine Mutter muss ins Heim"), session=db_clean, llm=_fake_clarify_only()
    )
    assert state.disposition == Disposition.clarify
    block = state.final_response.blocks[0]
    assert block.type == "clarifying_question"
    assert block.question_text == Q_STEP1
    assert state.active_pathway_id is not None
    assert "ResolvePathway" in state.audit.nodes_traversed
    # Pathway-Clarify ist deterministisch: nur scope + intent gehen ans LLM, keine Clarify-Frage.
    assert len(state.audit.llm_calls) == 2


async def test_turn2_advances_to_second_step_via_branch(db_clean):
    """Turn 2: Antwort 'true' folgt dem Branch zu Step 2."""
    await _seed_pathway(db_clean)
    state = await run_consultation(
        _turn("ja", pathway_answers={"krankenhaus_aktuell": "true"}),
        session=db_clean,
        llm=_fake_clarify_only(),
    )
    assert state.disposition == Disposition.clarify
    assert state.final_response.blocks[0].question_text == Q_STEP2


async def test_pathway_completes_and_presents_grounded(db_clean):
    """Beide Schritte beantwortet → Pathway vollständig → fokussierte Suche → Present."""
    cv = await _seed_pathway(db_clean)
    state = await run_consultation(
        _turn(
            "ja",
            pathway_answers={"krankenhaus_aktuell": "true", "pflegegrad_vorhanden": "true"},
        ),
        session=db_clean,
        llm=_fake_full(cv.id),
    )
    assert state.disposition == Disposition.presented
    assert state.audit.validation_passed is True
    assert str(cv.id) in state.audit.evidence_claim_version_ids
    # topic_hint hat die Suche fokussiert (BuildRetrievalPlan → Coverage-Override).
    assert state.retrieval_topic_focus == "stationaere_pflege"
    assert state.coverage_aspect_override == {"heimunterbringung": ["stationaere_pflege"]}
    assert "BuildRetrievalPlan" in state.audit.nodes_traversed


async def test_branch_false_skips_second_step(db_clean):
    """Antwort 'false' an Step 1 führt direkt zum Pathway-Ende — Step 2 wird nie gefragt."""
    cv = await _seed_pathway(db_clean)
    state = await run_consultation(
        _turn("nein", pathway_answers={"krankenhaus_aktuell": "false"}),
        session=db_clean,
        llm=_fake_full(cv.id),
    )
    assert state.disposition == Disposition.presented
    # Fokus stammt aus dem terminalen Branch-Modifier.
    assert state.retrieval_topic_focus == "stationaere_pflege"


async def test_pathway_drives_clarification_not_intent(db_clean):
    """
    Auch wenn LLM-2 missing_information meldet, übernimmt der Pathway deterministisch.
    Die gestellte Frage ist das Pathway-Template, keine frei formulierte LLM-3-Frage.
    """
    await _seed_pathway(db_clean)
    fake = FakeLLMClient(
        responses={
            LLMTouchpoint.scope_safety: _cls(),
            LLMTouchpoint.intent: _intent(missing=("region",)),
        }
    )
    state = await run_consultation(_turn("Hilfe"), session=db_clean, llm=fake)
    assert state.disposition == Disposition.clarify
    assert state.final_response.blocks[0].question_text == Q_STEP1
