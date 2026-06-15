"""
Referenz-Adapter: Anthropic Claude hinter dem LLM-Port.

WICHTIG: Der produktive LLM-Anbieter ist eine offene menschliche Entscheidung
(Architektur §6). Dieser Adapter ist die *empfohlene Default-Referenz*, nicht
eine Festlegung. Er ist gegen `careapp.llm.port.LLMClient` austauschbar.

Verträge aus Layer 3 §1, die hier umgesetzt werden:
- Drei-Kanal-Trennung: `system_rules` → `system`; Daten-Kanäle + Task → Nutzerinhalt.
- Schema-erzwungene Ausgabe: `messages.parse(output_format=...)`.
- Minimale Fähigkeiten: keine Tools, kein Web/DB-Zugriff.
- Budget: `max_output_tokens` → `max_tokens`, Timeout pro Aufruf.
- Metering (L3-2/L4-3): input_tokens, output_tokens, latency_ms, cost_usd je Aufruf.

Das `anthropic`-Paket ist eine optionale Abhängigkeit (extra `llm`) und wird
lazy importiert, damit der deterministische Kern ohne SDK testbar bleibt.
"""

import dataclasses
import time
from typing import Literal, Optional

from careapp.llm.port import LLMCallAudit, LLMRequest, LLMResult

EffortLevel = Literal["low", "medium", "high", "xhigh", "max"]

# Default-Modell laut Anthropic-Empfehlung (Stand: aktuelle Modellliste).
# Der konkrete Wert fließt pro Aufruf aus `request.audit.model_id`.
DEFAULT_MODEL_ID = "claude-opus-4-8"

# Preistabelle (Input $/M Token, Output $/M Token). Stand: 2026-06.
# Dient der Kostenschätzung im Audit — keine Abrechnungsgrundlage.
_COST_TABLE: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-fable-5": (10.00, 50.00),
}


def _compute_cost(model_id: str, input_tokens: int, output_tokens: int) -> Optional[float]:
    entry = _COST_TABLE.get(model_id)
    if entry is None:
        return None
    inp_per_m, out_per_m = entry
    return round((input_tokens * inp_per_m + output_tokens * out_per_m) / 1_000_000, 8)


class AnthropicLLMClient:
    """Implementiert `LLMClient` mit dem Anthropic Python SDK."""

    def __init__(
        self,
        *,
        effort: EffortLevel = "high",
        client: object | None = None,
    ) -> None:
        if client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - abhängig von Installation
                raise RuntimeError(
                    "Das 'anthropic'-Paket ist nicht installiert. "
                    "Installiere das Extra: `uv sync --extra llm`."
                ) from exc
            client = anthropic.Anthropic()
        self._client = client
        self._effort: EffortLevel = effort

    def complete_structured(self, request: LLMRequest) -> LLMResult:
        # Drei-Kanal: System-Regeln vertraut; Daten + Task als Nutzerinhalt (DATEN).
        system = request.prompt.system_rules
        data_payload = request.prompt.render_data_payload()
        user_content = f"{data_payload}\n\n[TASK]\n{request.prompt.task}".strip()

        t0 = time.monotonic()
        try:
            response = self._client.with_options(
                timeout=request.budget.timeout_seconds
            ).messages.parse(
                model=request.audit.model_id or DEFAULT_MODEL_ID,
                max_tokens=request.budget.max_output_tokens,
                thinking={"type": "adaptive"},
                output_config={"effort": self._effort},
                system=system,
                messages=[{"role": "user", "content": user_content}],
                output_format=request.response_schema,
            )
        except Exception as exc:  # noqa: BLE001 — jede Anbieter-/Netzwerkfehlerklasse → Fallback
            return LLMResult(
                parsed=None,
                raw_text="",
                parse_error=f"llm call failed: {type(exc).__name__}: {exc}",
                audit=request.audit,  # kein Metering bei Verbindungsfehlern
            )

        latency_ms = round((time.monotonic() - t0) * 1000)

        usage = getattr(response, "usage", None)
        input_tokens: Optional[int] = getattr(usage, "input_tokens", None)
        output_tokens: Optional[int] = getattr(usage, "output_tokens", None)
        cost_usd: Optional[float] = None
        if input_tokens is not None and output_tokens is not None:
            cost_usd = _compute_cost(
                request.audit.model_id or DEFAULT_MODEL_ID, input_tokens, output_tokens
            )

        metered_audit = dataclasses.replace(
            request.audit,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
        )

        parsed = getattr(response, "parsed_output", None)
        raw_text = next(
            (b.text for b in getattr(response, "content", []) if getattr(b, "type", None) == "text"),
            "",
        )

        # Schema-/Refusal-Fehler → kein Freitext-Passthrough (§1.2).
        if parsed is None or not isinstance(parsed, request.response_schema):
            return LLMResult(
                parsed=None,
                raw_text=raw_text,
                parse_error="model returned no schema-valid output",
                audit=metered_audit,
            )

        return LLMResult(parsed=parsed, raw_text=raw_text, parse_error=None, audit=metered_audit)
