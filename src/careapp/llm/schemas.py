"""
Strikte Ausgabeschemata für LLM-1 bis LLM-5 (Layer 3a, §2).

Jede LLM-Ausgabe wird gegen eines dieser Pydantic-Schemas validiert
(schema-erzwungene Ausgabe, §1.2). Parse-/Schema-Fehler → sicherer Fallback
(siehe `fallback.py`), niemals Durchreichen von Freitext.

Diese Schemas sind anbieter-agnostisch. Sie funktionieren mit Anthropic
`messages.parse(output_format=...)` ebenso wie mit jedem anderen
Structured-Output-Mechanismus.
"""

import uuid
from enum import Enum
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from careapp.domain.evidence_builder import StructuredValueRecord


# ------------------------------------------------------------------ #
# Gemeinsame Basis: striktes Schema, keine zusätzlichen Felder         #
# ------------------------------------------------------------------ #


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ------------------------------------------------------------------ #
# LLM-1 — Scope- & Safety-Klassifikation                              #
# ------------------------------------------------------------------ #


class RecommendedAction(str, Enum):
    answer_in_scope = "answer_in_scope"
    ask_clarifying_question = "ask_clarifying_question"
    safe_fallback = "safe_fallback"
    out_of_scope_notice = "out_of_scope_notice"
    safety_notice = "safety_notice"


class ScopeSafetyClassification(_StrictModel):
    """
    LLM-1-Ausgabe. Enumerierte Labels + Konfidenz, kein Freitext.

    Wichtig: Diese Klassifikation entscheidet NICHT allein über Scope.
    Sie wird mit deterministischen Regeln + Fallback kombiniert
    (`scope_safety.decide_scope_safety`).
    """

    in_scope: bool
    requires_diagnosis_triage_treatment: bool
    requires_individual_eligibility_decision: bool
    safety_signal: bool
    prompt_injection_suspected: bool
    confidence: float = Field(ge=0.0, le=1.0)
    # Safety-Pfad darf NUR vorab freigegebene safety_notice-Bausteine wählen (§2 LLM-1).
    safety_notice_id: Optional[str] = None


# ------------------------------------------------------------------ #
# LLM-2 — Anliegen verstehen                                          #
# ------------------------------------------------------------------ #


class ConfirmedFact(_StrictModel):
    key: str
    value: str
    source: str  # z. B. "user_turn_17" — Provenienz des bestätigten Fakts


class IntentNextAction(str, Enum):
    ask_clarifying_question = "ask_clarifying_question"
    proceed_to_retrieval = "proceed_to_retrieval"
    safe_fallback = "safe_fallback"


class IntentUnderstanding(_StrictModel):
    """LLM-2-Ausgabe. Erzeugt KEINE Fachantwort, nur strukturierte Interpretation."""

    intent_hypotheses: tuple[str, ...]
    life_situation_hypotheses: tuple[str, ...]
    confirmed_facts: tuple[ConfirmedFact, ...]
    missing_information: tuple[str, ...]
    medical_advice_requested: bool
    recommended_next_action: IntentNextAction


# ------------------------------------------------------------------ #
# LLM-3 — Rückfrage formulieren                                       #
# ------------------------------------------------------------------ #


class AnswerOption(_StrictModel):
    value: str
    label: str


class ClarifyingQuestion(_StrictModel):
    """LLM-3-Ausgabe. Frage zu genau den fehlenden, nötigen Daten."""

    question_text: str
    addresses_missing_keys: tuple[str, ...]
    options: tuple[AnswerOption, ...] = ()


# ------------------------------------------------------------------ #
# LLM-4 — Suchbegriffe vorschlagen                                    #
# ------------------------------------------------------------------ #


class RetrievalTermSuggestions(_StrictModel):
    """
    LLM-4-Ausgabe. Nur Vorschläge — der typisierte RetrievalPlan wird
    serverseitig gebaut; Status-/Mandanten-/Regions-/Gültigkeitsfilter
    werden NICHT vom LLM gesetzt.
    """

    query_terms: tuple[str, ...]
    topics: tuple[str, ...]


# ------------------------------------------------------------------ #
# LLM-5 — Grounded Response Composer (Block-Schema)                   #
# ------------------------------------------------------------------ #


class StructuredValueOut(_StrictModel):
    """Strukturierter Wert in einer factual_statement-Aussage (wird vom Validator exakt geprüft)."""

    kind: str
    value: str
    unit: Optional[str] = None

    def to_record(self) -> StructuredValueRecord:
        return StructuredValueRecord(kind=self.kind, value=self.value, unit=self.unit)


class EmpathyBlock(_StrictModel):
    type: Literal["empathy"] = "empathy"
    text: str


class FactualStatementBlock(_StrictModel):
    """
    Genau EINE unabhängig prüfbare Aussage mit mindestens einer claim_version_id.
    Keine Aussage ohne claim_version_id (§2 LLM-5, Verbot).
    """

    type: Literal["factual_statement"] = "factual_statement"
    text: str
    claim_version_ids: tuple[uuid.UUID, ...] = Field(min_length=1)
    structured_values: tuple[StructuredValueOut, ...] = ()


class ClarifyingQuestionBlock(_StrictModel):
    type: Literal["clarifying_question"] = "clarifying_question"
    question_text: str


class FallbackBlock(_StrictModel):
    type: Literal["fallback"] = "fallback"
    text: str


OutputBlock = Annotated[
    Union[EmpathyBlock, FactualStatementBlock, ClarifyingQuestionBlock, FallbackBlock],
    Field(discriminator="type"),
]


class ComposerResponse(_StrictModel):
    """LLM-5-Ausgabe. Liste erlaubter Blöcke; geht IMMER durch den Validator (Layer 2 §4.4)."""

    blocks: tuple[OutputBlock, ...]


# ------------------------------------------------------------------ #
# Output-Block-Allowlist (§3b, neue Pflicht #4 / T11+T12)             #
# ------------------------------------------------------------------ #

ALLOWED_BLOCK_TYPES: frozenset[str] = frozenset(
    {"empathy", "factual_statement", "clarifying_question", "fallback"}
)


class DisallowedBlockError(ValueError):
    """Ein Block-Typ außerhalb der Allowlist hat versucht, die UI zu erreichen."""


def enforce_block_allowlist(blocks: tuple[OutputBlock, ...]) -> tuple[OutputBlock, ...]:
    """
    Serverseitige Durchsetzung der Block-Allowlist. Nur definierte Blocktypen
    dürfen die UI erreichen; alles andere wird verworfen (fail-closed).
    """
    for block in blocks:
        block_type = getattr(block, "type", None)
        if block_type not in ALLOWED_BLOCK_TYPES:
            raise DisallowedBlockError(f"Block-Typ {block_type!r} nicht in Allowlist")
    return blocks
