"""
Integrationstests für den Grounded Response Composer (Layer 3.2, LLM-5).

Verdrahtet Layer 2 (Evidence Builder + Validator, echte Supabase-Instanz) mit
dem Layer-3-Port. Kein Live-LLM: der `FakeLLMClient` liefert deterministische
`ComposerResponse`-Instanzen. Geprüft wird die Bridge Composer→Validator (D8)
und das Fail-closed-Verhalten (§1.2 / §4.5).
"""

import uuid

import pytest

from careapp.domain.evidence_builder import build_evidence_package
from careapp.llm.composer import compose_grounded_response
from careapp.llm.port import FakeLLMClient, LLMTouchpoint
from careapp.llm.schemas import (
    ClarifyingQuestionBlock,
    ComposerResponse,
    EmpathyBlock,
    FactualStatementBlock,
    StructuredValueOut,
)

# Geteilte Test-Bausteine aus Layer 2 (tests ist ein Paket).
from tests.db.test_layer2 import _TRUNCATE_ALL, BASE_CTX, _Builder

FALLBACK_WORTLAUT = "Dazu liegen mir keine geprüften Informationen vor."


@pytest.fixture
async def db_clean(session):
    """Leer räumen vor und nach jedem Test."""
    await session.execute(_TRUNCATE_ALL)
    await session.commit()
    yield session
    await session.execute(_TRUNCATE_ALL)
    await session.commit()


def _fake(composer_response: ComposerResponse | None = None, *, fail: bool = False) -> FakeLLMClient:
    if fail:
        return FakeLLMClient(fail_touchpoints=frozenset({LLMTouchpoint.compose}))
    assert composer_response is not None
    return FakeLLMClient(responses={LLMTouchpoint.compose: composer_response})


async def _seed_one_cv(db_clean, **kwargs):
    """Quellobjekte + eine vollständige published CV anlegen, Package bauen."""
    b = _Builder()
    for obj in b.source_objects():
        db_clean.add(obj)
    await db_clean.commit()
    cv = await b.insert_full_cv(db_clean, **kwargs)
    pkg = await build_evidence_package(db_clean, BASE_CTX)
    return cv, pkg


# ------------------------------------------------------------------ #
# Happy Path: belegte Aussage → unverändert durchgereicht             #
# ------------------------------------------------------------------ #


async def test_composer_happy_path(db_clean):
    """Composer zitiert eine echte CV-ID → Validierung besteht, kein Fallback."""
    cv, pkg = await _seed_one_cv(db_clean)

    response = ComposerResponse(
        blocks=(
            EmpathyBlock(text="Das klingt nach einer belastenden Situation."),
            FactualStatementBlock(
                text="Es besteht ein Anspruch auf vollstationäre Pflege.",
                claim_version_ids=(cv.id,),
            ),
        )
    )
    outcome = await compose_grounded_response(
        session=db_clean,
        client=_fake(response),
        ctx=BASE_CTX,
        evidence_package=pkg,
        user_input="Meine Mutter muss ins Heim",
    )

    assert not outcome.used_fallback
    assert outcome.validation is not None and outcome.validation.passed
    block_types = [bl.type for bl in outcome.response.blocks]
    assert "empathy" in block_types
    assert "factual_statement" in block_types
    assert outcome.audit.touchpoint == LLMTouchpoint.compose


async def test_composer_no_factual_statements_passthrough(db_clean):
    """Nur Empathie + Rückfrage (keine fachliche Aussage) → nichts zu validieren, kein Fallback."""
    _cv, pkg = await _seed_one_cv(db_clean)

    response = ComposerResponse(
        blocks=(
            EmpathyBlock(text="Ich verstehe."),
            ClarifyingQuestionBlock(question_text="In welchem Kreis wohnt die Person?"),
        )
    )
    outcome = await compose_grounded_response(
        session=db_clean, client=_fake(response), ctx=BASE_CTX, evidence_package=pkg
    )

    assert not outcome.used_fallback
    assert outcome.validation is not None and outcome.validation.passed
    assert len(outcome.response.blocks) == 2


async def test_composer_valid_structured_value_passes(db_clean):
    """Behaupteter strukturierter Wert == Quelle → besteht."""
    cv, pkg = await _seed_one_cv(db_clean, with_structured_value="1000")

    response = ComposerResponse(
        blocks=(
            FactualStatementBlock(
                text="Der Eigenanteil beträgt 1000 EUR.",
                claim_version_ids=(cv.id,),
                structured_values=(
                    StructuredValueOut(kind="amount_eur", value="1000", unit="EUR"),
                ),
            ),
        )
    )
    outcome = await compose_grounded_response(
        session=db_clean, client=_fake(response), ctx=BASE_CTX, evidence_package=pkg
    )

    assert not outcome.used_fallback
    assert outcome.validation is not None and outcome.validation.passed


# ------------------------------------------------------------------ #
# Fail-closed: jede unbelegbare Aussage → ganzer Fallback             #
# ------------------------------------------------------------------ #


async def test_composer_invented_cv_id_falls_back(db_clean):
    """Erfundene claim_version_id (nicht in DB) → Validator scheitert → Fallback (D8)."""
    _cv, pkg = await _seed_one_cv(db_clean)

    response = ComposerResponse(
        blocks=(
            FactualStatementBlock(
                text="Eine frei erfundene Behauptung.",
                claim_version_ids=(uuid.uuid4(),),
            ),
        )
    )
    outcome = await compose_grounded_response(
        session=db_clean, client=_fake(response), ctx=BASE_CTX, evidence_package=pkg
    )

    assert outcome.used_fallback
    assert outcome.fallback_reason == "validation_failed"
    assert outcome.validation is not None and not outcome.validation.passed
    assert len(outcome.response.blocks) == 1
    assert outcome.response.blocks[0].type == "fallback"
    assert outcome.response.blocks[0].text == FALLBACK_WORTLAUT


async def test_composer_structured_value_mismatch_falls_back(db_clean):
    """Behaupteter Wert weicht von der Quelle ab → Validator scheitert → Fallback (D3)."""
    cv, pkg = await _seed_one_cv(db_clean, with_structured_value="1000")

    response = ComposerResponse(
        blocks=(
            FactualStatementBlock(
                text="Der Betrag liegt bei 2000 EUR.",
                claim_version_ids=(cv.id,),
                structured_values=(
                    StructuredValueOut(kind="amount_eur", value="2000", unit="EUR"),
                ),
            ),
        )
    )
    outcome = await compose_grounded_response(
        session=db_clean, client=_fake(response), ctx=BASE_CTX, evidence_package=pkg
    )

    assert outcome.used_fallback
    assert outcome.fallback_reason == "validation_failed"
    assert outcome.response.blocks[0].text == FALLBACK_WORTLAUT


async def test_composer_parse_error_falls_back(db_clean):
    """Parse-/Schemafehler des LLM → sicherer Fallback, keine Validierung, kein Passthrough."""
    _cv, pkg = await _seed_one_cv(db_clean)

    outcome = await compose_grounded_response(
        session=db_clean, client=_fake(fail=True), ctx=BASE_CTX, evidence_package=pkg
    )

    assert outcome.used_fallback
    assert outcome.fallback_reason == "schema_or_parse_error"
    assert outcome.validation is None
    assert outcome.response.blocks[0].type == "fallback"
    assert outcome.response.blocks[0].text == FALLBACK_WORTLAUT
