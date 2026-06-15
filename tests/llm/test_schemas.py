"""
Tests für die LLM-Ausgabeschemata (Layer 3a, §2) und die Output-Block-Allowlist.
Reine Python-Logik — kein LLM, keine DB.
"""

import uuid

import pytest
from pydantic import ValidationError

from careapp.domain.evidence_builder import StructuredValueRecord
from careapp.llm.schemas import (
    ALLOWED_BLOCK_TYPES,
    ClarifyingQuestionBlock,
    ComposerResponse,
    DisallowedBlockError,
    EmpathyBlock,
    FactualStatementBlock,
    FallbackBlock,
    IntentNextAction,
    IntentUnderstanding,
    ScopeSafetyClassification,
    StructuredValueOut,
    enforce_block_allowlist,
)

CV_ID = uuid.UUID("00000000-0000-0000-0000-000000000011")


# ---- LLM-1 ----

def test_scope_safety_classification_valid():
    c = ScopeSafetyClassification(
        in_scope=True,
        requires_diagnosis_triage_treatment=False,
        requires_individual_eligibility_decision=False,
        safety_signal=False,
        prompt_injection_suspected=False,
        confidence=0.9,
    )
    assert c.in_scope
    assert c.safety_notice_id is None


def test_scope_safety_confidence_out_of_range_rejected():
    with pytest.raises(ValidationError):
        ScopeSafetyClassification(
            in_scope=True,
            requires_diagnosis_triage_treatment=False,
            requires_individual_eligibility_decision=False,
            safety_signal=False,
            prompt_injection_suspected=False,
            confidence=1.5,
        )


def test_extra_fields_forbidden():
    """Striktes Schema — unerwartete Felder werden abgelehnt (kein Schmuggeln)."""
    with pytest.raises(ValidationError):
        ScopeSafetyClassification(
            in_scope=True,
            requires_diagnosis_triage_treatment=False,
            requires_individual_eligibility_decision=False,
            safety_signal=False,
            prompt_injection_suspected=False,
            confidence=0.9,
            free_text="injected payload",
        )


# ---- LLM-2 ----

def test_intent_understanding_from_doc_example():
    data = {
        "intent_hypotheses": ["hospital_discharge_support"],
        "life_situation_hypotheses": ["discharge_from_hospital"],
        "confirmed_facts": [
            {"key": "affected_person", "value": "mother", "source": "user_turn_17"}
        ],
        "missing_information": ["region"],
        "medical_advice_requested": False,
        "recommended_next_action": "ask_clarifying_question",
    }
    parsed = IntentUnderstanding.model_validate(data)
    assert parsed.recommended_next_action == IntentNextAction.ask_clarifying_question
    assert parsed.confirmed_facts[0].source == "user_turn_17"


# ---- LLM-5 Composer ----

def test_factual_statement_requires_claim_version_id():
    """Keine Aussage ohne claim_version_id (§2 LLM-5)."""
    with pytest.raises(ValidationError):
        FactualStatementBlock(text="Behauptung ohne Beleg", claim_version_ids=())


def test_factual_statement_valid_with_id():
    block = FactualStatementBlock(
        text="SYNTHETISCH: Anspruch auf vollstationäre Pflege.",
        claim_version_ids=(CV_ID,),
        structured_values=(StructuredValueOut(kind="amount_eur", value="0", unit="EUR"),),
    )
    assert block.type == "factual_statement"
    assert block.claim_version_ids == (CV_ID,)


def test_structured_value_to_record():
    sv = StructuredValueOut(kind="amount_eur", value="1000", unit="EUR")
    rec = sv.to_record()
    assert rec == StructuredValueRecord(kind="amount_eur", value="1000", unit="EUR")


def test_composer_response_discriminated_union_roundtrip():
    resp = ComposerResponse(
        blocks=(
            EmpathyBlock(text="Das ist eine schwierige Situation."),
            FactualStatementBlock(text="SYNTHETISCH.", claim_version_ids=(CV_ID,)),
        )
    )
    # Roundtrip durch JSON erzwingt den Discriminator
    reparsed = ComposerResponse.model_validate_json(resp.model_dump_json())
    assert reparsed.blocks[0].type == "empathy"
    assert reparsed.blocks[1].type == "factual_statement"


# ---- Output-Block-Allowlist (T11/T12) ----

def test_allowlist_passes_known_blocks():
    blocks = (
        EmpathyBlock(text="x"),
        FactualStatementBlock(text="y", claim_version_ids=(CV_ID,)),
        ClarifyingQuestionBlock(question_text="In welchem Kreis wohnt die Person?"),
        FallbackBlock(text="z"),
    )
    assert enforce_block_allowlist(blocks) == blocks


def test_allowlist_rejects_unknown_type():
    class RogueBlock:
        type = "raw_html"
        text = "<script>alert(1)</script>"

    with pytest.raises(DisallowedBlockError):
        enforce_block_allowlist((RogueBlock(),))


def test_allowlist_contents():
    assert ALLOWED_BLOCK_TYPES == frozenset(
        {"empathy", "factual_statement", "clarifying_question", "fallback"}
    )
