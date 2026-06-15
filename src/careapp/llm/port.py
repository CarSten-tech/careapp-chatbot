"""
Anbieter-agnostischer LLM-Port (Layer 3, §1.3 + §6).

Der Laufzeitkern spricht ausschließlich gegen `LLMClient`. Der konkrete
Anbieter (Anthropic, anderer Host) ist eine offene menschliche Entscheidung
(Architektur §6) und wird hinter diesem Port gekapselt.

Hier verdrahtet:
- Drei-Kanal-Trennung als Datentyp (`LLMRequest` trägt System/Daten/Task getrennt).
- Schema-erzwungene Ausgabe (`response_schema`).
- Audit von Prompt- und Modellversion (`LLMCallAudit`).
- Budget-Felder pro Aufruf (`LLMCallBudget`) — Verdrahtung der Werte in Layer 4.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Protocol, runtime_checkable

from pydantic import BaseModel

from careapp.llm.channels import ThreeChannelPrompt


class LLMTouchpoint(str, Enum):
    """Die fünf Laufzeit-Berührungspunkte (§2)."""

    scope_safety = "scope_safety"          # LLM-1
    intent = "intent"                      # LLM-2
    clarify = "clarify"                    # LLM-3
    retrieval_terms = "retrieval_terms"    # LLM-4
    compose = "compose"                    # LLM-5


@dataclass(frozen=True)
class LLMCallBudget:
    """Token-/Zeit-/Schleifenbudget pro Aufruf (§1.3 / T10). Werte verdrahtet in Layer 4."""

    max_input_tokens: int
    max_output_tokens: int
    timeout_seconds: float
    max_loops: int = 1


@dataclass(frozen=True)
class LLMCallAudit:
    """
    Geht ins Audit (§1.3, DoD: Prompt-/Modellversion + Token-/Kosten-/Latenzwerte).

    Metering-Felder sind None bei FakeLLMClient / wenn der Adapter keine Werte
    zurückgibt (z. B. Netzwerkfehler). Aggregation in ConsultationAudit.
    """

    touchpoint: LLMTouchpoint
    prompt_version: str
    model_id: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    latency_ms: Optional[int] = None
    cost_usd: Optional[float] = None


@dataclass(frozen=True)
class LLMRequest:
    """
    Eine schema-erzwungene Modellanfrage mit Drei-Kanal-Trennung.

    `prompt` hält System-Regeln, Daten-Kanäle (Nutzereingabe, Evidence/Facts)
    und Task strukturell getrennt (§1.1). `response_schema` erzwingt das
    Ausgabeschema (§1.2).
    """

    prompt: ThreeChannelPrompt
    response_schema: type[BaseModel]
    audit: LLMCallAudit
    budget: LLMCallBudget


@dataclass(frozen=True)
class LLMResult:
    """
    Ergebnis eines LLM-Aufrufs. `parsed` ist None bei Parse-/Schema-Fehler —
    dann MUSS der Aufrufer auf den sicheren Fallback gehen (kein Freitext-Passthrough).
    """

    parsed: Optional[BaseModel]
    raw_text: str
    parse_error: Optional[str]
    audit: LLMCallAudit

    @property
    def ok(self) -> bool:
        return self.parsed is not None and self.parse_error is None


@runtime_checkable
class LLMClient(Protocol):
    """
    Minimaler Port. Eine einzige Fähigkeit: schema-validierte Vervollständigung.
    Kein SQL, DB, Web oder Dateizugriff (§1.3, minimale Fähigkeiten).
    """

    def complete_structured(self, request: LLMRequest) -> LLMResult:
        ...


# ------------------------------------------------------------------ #
# Test-Double — deterministisch, ohne Live-Aufruf                     #
# ------------------------------------------------------------------ #


@dataclass
class FakeLLMClient:
    """
    Deterministischer Stub für Tests. Gibt vorkonfigurierte Schema-Instanzen
    je Touchpoint zurück, oder simuliert einen Parse-Fehler.
    """

    responses: dict[LLMTouchpoint, BaseModel] = field(default_factory=dict)
    fail_touchpoints: frozenset[LLMTouchpoint] = frozenset()
    bad_raw_text: str = "{ this is not valid json"

    def complete_structured(self, request: LLMRequest) -> LLMResult:
        tp = request.audit.touchpoint
        if tp in self.fail_touchpoints:
            return LLMResult(
                parsed=None,
                raw_text=self.bad_raw_text,
                parse_error="simulated schema/parse failure",
                audit=request.audit,
            )
        parsed = self.responses.get(tp)
        if parsed is None:
            return LLMResult(
                parsed=None,
                raw_text="",
                parse_error=f"no canned response for touchpoint {tp.value}",
                audit=request.audit,
            )
        return LLMResult(
            parsed=parsed,
            raw_text=parsed.model_dump_json(),
            parse_error=None,
            audit=request.audit,
        )
