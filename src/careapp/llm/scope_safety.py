"""
Scope/Safety-Entscheidung als Kombination (Layer 3, §2 LLM-1 + DoD).

Die Prüfung darf NICHT allein aus der LLM-1-Antwort bestehen. Sie ist die
Kombination aus:
  1. deterministischen Regeln (serverseitig, kennen den Auth-Kontext),
  2. eng begrenzter LLM-Klassifikation,
  3. sicherem Fallback bei Unsicherheit/Parsefehler.

Leitprinzip (analog Validator/D8): Die LLM-Klassifikation darf nur VERSCHÄRFEN,
niemals erlauben. Sie kann Scope nicht gewähren, den die Regeln verweigern,
und sie kann ein Safety-Signal nur hinzufügen, nie entfernen.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from careapp.llm.schemas import RecommendedAction, ScopeSafetyClassification


class SafetyDisposition(str, Enum):
    proceed = "proceed"                  # in Scope, weiter zum Anliegen-Verständnis
    clarify = "clarify"                  # Rückfrage nötig
    out_of_scope = "out_of_scope"        # außerhalb Produkt-Scope → sichere Notiz
    safe_fallback = "safe_fallback"      # Unsicherheit/Parsefehler → Fallback
    safety_notice = "safety_notice"      # Safety-Signal → freigegebene safety_notice


@dataclass(frozen=True)
class DeterministicSignals:
    """
    Serverseitig ermittelte Signale, unabhängig vom LLM.

    `topic_in_allowed_scope`: kommt aus der redaktionell gepflegten Scope-Definition
    (nicht vom LLM). `hard_safety_trigger`: deterministischer Treffer (z. B.
    redaktionelle Krisen-Schlüsselbegriffsliste). `confidence_floor`: minimale
    Klassifikations-Konfidenz, unter der konservativ behandelt wird.
    """

    topic_in_allowed_scope: bool
    hard_safety_trigger: bool = False
    confidence_floor: float = 0.5
    approved_safety_notice_ids: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class ScopeSafetyDecision:
    disposition: SafetyDisposition
    safety_notice_id: Optional[str]
    reason: str


def decide_scope_safety(
    classification: Optional[ScopeSafetyClassification],
    signals: DeterministicSignals,
) -> ScopeSafetyDecision:
    """
    Kombiniert Regeln + Klassifikation + Fallback zu einer fail-closed-Entscheidung.

    Reihenfolge (konservativ, fail-closed):
      0. Klassifikation fehlt/Parsefehler        → safe_fallback
      1. irgendein Safety-Signal (Regel ODER LLM) → safety_notice (nur freigegebene ID)
      2. Diagnose/Triage/Behandlung verlangt      → out_of_scope (kein medizinischer Rat)
      3. Regel: Thema außerhalb Scope             → out_of_scope
      4. niedrige Konfidenz                        → safe_fallback
      5. individuelle Anspruchsentscheidung        → out_of_scope
      6. LLM hält out of scope                     → out_of_scope
      7. sonst                                      → proceed
    """
    # 0. Parsefehler / keine Klassifikation → konservativ
    if classification is None:
        return ScopeSafetyDecision(
            SafetyDisposition.safe_fallback, None, "no classification (parse error)"
        )

    # 1. Safety-Signal aus beliebiger Quelle. Nur freigegebene safety_notice-ID zulässig.
    if signals.hard_safety_trigger or classification.safety_signal:
        notice_id = classification.safety_notice_id
        if notice_id not in signals.approved_safety_notice_ids:
            # Safety-Signal, aber kein freigegebener Baustein wählbar → sicherer Fallback.
            return ScopeSafetyDecision(
                SafetyDisposition.safe_fallback,
                None,
                "safety signal without approved safety_notice",
            )
        return ScopeSafetyDecision(
            SafetyDisposition.safety_notice, notice_id, "safety signal"
        )

    # 2. Medizinische Diagnose/Triage/Behandlung verlangt → kein medizinischer Rat (T3).
    if classification.requires_diagnosis_triage_treatment:
        return ScopeSafetyDecision(
            SafetyDisposition.out_of_scope, None, "diagnosis/triage/treatment requested"
        )

    # 3. Deterministische Scope-Regel (kennt den freigegebenen Produkt-Scope).
    if not signals.topic_in_allowed_scope:
        return ScopeSafetyDecision(
            SafetyDisposition.out_of_scope, None, "topic outside allowed scope (rule)"
        )

    # 4. Niedrige Konfidenz → konservativ.
    if classification.confidence < signals.confidence_floor:
        return ScopeSafetyDecision(
            SafetyDisposition.safe_fallback,
            None,
            f"confidence {classification.confidence} < floor {signals.confidence_floor}",
        )

    # 5. Individuelle Anspruchsentscheidung verlangt → keine Anspruchsableitung (T5).
    if classification.requires_individual_eligibility_decision:
        return ScopeSafetyDecision(
            SafetyDisposition.out_of_scope,
            None,
            "individual eligibility decision requested",
        )

    # 6. LLM hält für out of scope (LLM darf nur verschärfen).
    if not classification.in_scope:
        return ScopeSafetyDecision(
            SafetyDisposition.out_of_scope, None, "classification: not in scope"
        )

    # 7. Alle Gates passiert → weiter.
    return ScopeSafetyDecision(SafetyDisposition.proceed, None, "in scope")


def action_for(decision: ScopeSafetyDecision) -> RecommendedAction:
    """Bildet die Entscheidung auf die enumerierte Folgeaktion ab."""
    return {
        SafetyDisposition.proceed: RecommendedAction.answer_in_scope,
        SafetyDisposition.clarify: RecommendedAction.ask_clarifying_question,
        SafetyDisposition.out_of_scope: RecommendedAction.out_of_scope_notice,
        SafetyDisposition.safe_fallback: RecommendedAction.safe_fallback,
        SafetyDisposition.safety_notice: RecommendedAction.safety_notice,
    }[decision.disposition]
