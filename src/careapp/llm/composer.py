"""
Grounded Response Composer (Layer 3a, LLM-5) + Bridge zum Validator (Layer 2 §4.4 / D8).

Der Composer ist der einzige Laufzeit-LLM-Aufruf, der eine fachliche Antwort
FORMULIERT. Er ist trotzdem keine Quelle der Wahrheit: jede fachliche Aussage,
die er erzeugt, ist eine BEHAUPTUNG und wird durch den deterministischen
Post-Generation-Validator (`validate_statements`) gegen die frisch geladene
Quelle geprüft, bevor sie die UI erreichen darf.

Ablauf:
  1. Evidence Package + bestätigte Fakten in die DATEN-Kanäle rendern
  2. Drei-Kanal-Prompt bauen (`build_composer_prompt`)
  3. Schema-erzwungenen LLM-Aufruf über den Port (`LLMClient.complete_structured`)
  4. Output-Block-Allowlist serverseitig durchsetzen (T11/T12)
  5. Jede factual_statement → FactualStatement, durch `validate_statements` (D8)

Fail-closed (§1.2 + §4.5): Parse-/Schemafehler, ein nicht erlaubter Blocktyp
oder eine fehlgeschlagene Validierung führen IMMER zum sicheren Fallback —
niemals zu Freitext-Passthrough, niemals zu teilweise ungeprüfter Ausgabe.
"""

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from careapp.domain.eligibility import RequestContext
from careapp.domain.evidence_builder import EvidencePackage
from careapp.domain.validator import (
    FactualStatement,
    ValidationReport,
    validate_statements,
)
from careapp.llm.channels import build_composer_prompt
from careapp.llm.fallback import fallback_composer_response
from careapp.llm.port import (
    LLMCallAudit,
    LLMCallBudget,
    LLMClient,
    LLMRequest,
    LLMTouchpoint,
)
from careapp.llm.schemas import (
    ComposerResponse,
    ConfirmedFact,
    DisallowedBlockError,
    FactualStatementBlock,
    OutputBlock,
    enforce_block_allowlist,
)

# Prompt-Version geht ins Audit (§1.3, DoD). Bei Prompt-Änderung erhöhen.
COMPOSER_PROMPT_VERSION = "composer-v1"

# Nur ein Audit-/Referenzlabel — der konkrete Anbieter ist die injizierte
# `LLMClient`-Implementierung (Anbieterwahl offen, Architektur §6). Laut
# Kostenanalyse ist Sonnet für LLM-5 (reine Ausformulierung) ausreichend;
# Layer 4 / Betreiber überschreiben pro Aufruf.
DEFAULT_COMPOSER_MODEL_ID = "claude-sonnet-4-6"

# Platzhalter-Budget. Konkrete Werte werden in Layer 4 verdrahtet (offene
# Entscheidung). Hier nur sinnvolle, konservative Obergrenzen.
DEFAULT_COMPOSER_BUDGET = LLMCallBudget(
    max_input_tokens=8000,
    max_output_tokens=1500,
    timeout_seconds=30.0,
    max_loops=1,
)


@dataclass(frozen=True)
class ComposerOutcome:
    """
    Ergebnis des Composers, fertig für die Orchestrierung (Layer 4).

    `response` enthält ausschließlich UI-sichere Blöcke: entweder die
    validierte Composer-Ausgabe oder den sicheren Fallback. `used_fallback`
    und `fallback_reason` machen die Entscheidung im Audit nachvollziehbar.
    """

    response: ComposerResponse
    validation: Optional[ValidationReport]
    used_fallback: bool
    fallback_reason: Optional[str]
    audit: LLMCallAudit


def render_evidence_text(package: EvidencePackage) -> str:
    """
    Rendert das Evidence Package in den `<evidence>`-DATEN-Kanal.

    Enthält ausschließlich gefrorene, geprüfte Aussagen + claim_version_id +
    Belegzitat + strukturierte Werte — keine freien Dokumentinhalte. Die
    claim_version_id ist nötig, damit der Composer sie in der Ausgabe zitieren
    kann; der Validator prüft sie anschließend gegen die frische Quelle.

    T2-VORBEDINGUNG (redaktioneller Workflow, NICHT hier): Eine Passage wird erst
    Beleg, nachdem der Import/Review sie aktiv auf eingebettete Instruktionen /
    aktive Inhalte geprüft hat (Architektur §3b Pflicht #1). Zur Laufzeit härtet
    `channels.neutralize_delimiters` zusätzlich gegen Kanal-Ausbruch.
    """
    lines: list[str] = []
    for item in package.items:
        lines.append(f"[claim_version_id={item.claim_version_id}]")
        lines.append(f"Aussage: {item.statement_text}")
        lines.append(f'Beleg: "{item.carrying_quote}"')
        for sv in item.structured_values:
            unit = f" {sv.unit}" if sv.unit else ""
            lines.append(f"Wert: {sv.kind}={sv.value}{unit}")
        lines.append("")
    return "\n".join(lines).strip()


def render_confirmed_facts(facts: tuple[ConfirmedFact, ...]) -> str:
    """Rendert bestätigte Fakten als `key=value`-Zeilen (nur Anrede/Bezug, keine Fachquelle)."""
    return "\n".join(f"{f.key}={f.value}" for f in facts)


def _statements_from_blocks(blocks: tuple[OutputBlock, ...]) -> list[FactualStatement]:
    """
    Bridge: jede factual_statement des Composers wird zu einer prüfbaren
    Behauptung (`FactualStatement`). Empathie-/Rückfrage-/Fallback-Blöcke tragen
    keine fachliche Aussage und werden nicht validiert.
    """
    statements: list[FactualStatement] = []
    for block in blocks:
        if isinstance(block, FactualStatementBlock):
            statements.append(
                FactualStatement(
                    claim_version_ids=block.claim_version_ids,
                    asserted_structured_values=tuple(
                        sv.to_record() for sv in block.structured_values
                    ),
                )
            )
    return statements


def _fallback_outcome(
    audit: LLMCallAudit,
    reason: str,
    validation: Optional[ValidationReport],
) -> ComposerOutcome:
    return ComposerOutcome(
        response=fallback_composer_response(),
        validation=validation,
        used_fallback=True,
        fallback_reason=reason,
        audit=audit,
    )


async def compose_grounded_response(
    *,
    session: AsyncSession,
    client: LLMClient,
    ctx: RequestContext,
    evidence_package: EvidencePackage,
    user_input: str = "",
    confirmed_facts: tuple[ConfirmedFact, ...] = (),
    model_id: str = DEFAULT_COMPOSER_MODEL_ID,
    budget: LLMCallBudget = DEFAULT_COMPOSER_BUDGET,
) -> ComposerOutcome:
    """
    Formuliert eine geerdete Antwort und lässt sie deterministisch validieren.

    Gibt IMMER eine UI-sichere `ComposerResponse` zurück — entweder die
    validierte Ausgabe oder den Fallback. Der Aufrufer (Layer 4) rendert
    `outcome.response` direkt.
    """
    prompt = build_composer_prompt(
        evidence_text=render_evidence_text(evidence_package),
        confirmed_facts_text=render_confirmed_facts(confirmed_facts),
        locale=ctx.locale,
        user_input=user_input,
    )
    audit = LLMCallAudit(
        touchpoint=LLMTouchpoint.compose,
        prompt_version=COMPOSER_PROMPT_VERSION,
        model_id=model_id,
    )
    result = client.complete_structured(
        LLMRequest(
            prompt=prompt,
            response_schema=ComposerResponse,
            audit=audit,
            budget=budget,
        )
    )

    # 1) Schema-Gate (§1.2): Parse-/Schemafehler → sicherer Fallback, kein Passthrough.
    if not result.ok or not isinstance(result.parsed, ComposerResponse):
        return _fallback_outcome(result.audit, "schema_or_parse_error", validation=None)
    response = result.parsed

    # 2) Output-Block-Allowlist serverseitig erzwingen (T11/T12).
    try:
        enforce_block_allowlist(response.blocks)
    except DisallowedBlockError as exc:
        return _fallback_outcome(result.audit, f"disallowed_block: {exc}", validation=None)

    # 3) Bridge → Validator (D8): jede fachliche Aussage frisch gegen die Quelle prüfen.
    #    Composer-Text ist Behauptung, kein Beleg.
    statements = _statements_from_blocks(response.blocks)
    report = await validate_statements(session, statements, ctx, evidence_package)

    # 4) Fail-closed: eine einzige nicht belegbare Aussage → ganze Antwort verwerfen.
    if report.fallback_required:
        return _fallback_outcome(result.audit, "validation_failed", validation=report)

    return ComposerOutcome(
        response=response,
        validation=report,
        used_fallback=False,
        fallback_reason=None,
        audit=result.audit,
    )
