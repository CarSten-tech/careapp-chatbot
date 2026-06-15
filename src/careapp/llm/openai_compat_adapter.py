"""
OpenAI-kompatibler LLM-Adapter (NVIDIA NIM, Together AI, etc.).

Implementiert den `LLMClient`-Port aus Layer 3 für jeden Anbieter, der die
OpenAI Chat-Completions-API spricht (Base-URL konfigurierbar).

Verträge aus Layer 3 §1, die hier umgesetzt werden:
- Drei-Kanal-Trennung: system_rules → system-Message; Daten + Task → user-Message.
- Schema-erzwungene Ausgabe: response_format=json_object + Pydantic-Parsing.
- Minimale Fähigkeiten: keine Tools, kein Web/DB-Zugriff.
- Budget: max_output_tokens, Timeout pro Aufruf.
- Metering: input_tokens (prompt_tokens), output_tokens (completion_tokens), latency_ms, cost_usd.

Das `openai`-Paket ist Teil des `llm`-Extras und wird lazy importiert.
"""

import dataclasses
import json
import time
from typing import Optional

from careapp.llm.port import LLMCallAudit, LLMRequest, LLMResult

# Preistabelle: (Input $/M Token, Output $/M Token). Nur für Audit-Schätzung.
_COST_TABLE: dict[str, tuple[float, float]] = {
    "moonshotai/kimi-k2.6": (0.14, 0.56),
    "meta/llama-3.3-70b-instruct": (0.23, 0.40),
    "mistralai/mistral-large-2-instruct": (2.00, 6.00),
}

DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL_ID = "moonshotai/kimi-k2.6"


def _compute_cost(model_id: str, input_tokens: int, output_tokens: int) -> Optional[float]:
    entry = _COST_TABLE.get(model_id)
    if entry is None:
        return None
    inp_per_m, out_per_m = entry
    return round((input_tokens * inp_per_m + output_tokens * out_per_m) / 1_000_000, 8)


class OpenAICompatLLMClient:
    """
    Implementiert `LLMClient` für OpenAI-kompatible APIs (NVIDIA NIM u.a.).

    Strukturierte Ausgabe: response_format=json_object + Pydantic model_validate_json().
    Das JSON-Schema wird in den System-Prompt eingebettet damit das Modell weiß
    welches Format erwartet wird.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        default_model_id: str = DEFAULT_MODEL_ID,
        client: object | None = None,
    ) -> None:
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError(
                    "Das 'openai'-Paket ist nicht installiert. "
                    "Installiere es: `uv sync --extra llm`."
                ) from exc
            client = OpenAI(api_key=api_key, base_url=base_url)
        self._client = client
        self._default_model_id = default_model_id

    def complete_structured(self, request: LLMRequest) -> LLMResult:
        model_id = request.audit.model_id or self._default_model_id

        # Drei-Kanal: System-Regeln + eingebettetes JSON-Schema → system-Message.
        # Daten-Kanäle + Task → user-Message.
        schema_json = json.dumps(
            request.response_schema.model_json_schema(),
            ensure_ascii=False,
            indent=2,
        )
        full_system = (
            f"{request.prompt.system_rules}\n\n"
            f"Antworte AUSSCHLIESSLICH mit gültigem JSON gemäß diesem Schema:\n"
            f"```json\n{schema_json}\n```\n"
            f"Kein Text außerhalb des JSON-Objekts, kein Markdown-Wrapper."
        )

        data_payload = request.prompt.render_data_payload()
        user_content = f"{data_payload}\n\n[TASK]\n{request.prompt.task}".strip()

        t0 = time.monotonic()
        try:
            response = self._client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": full_system},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                max_tokens=request.budget.max_output_tokens,
                timeout=request.budget.timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            return LLMResult(
                parsed=None,
                raw_text="",
                parse_error=f"llm call failed: {type(exc).__name__}: {exc}",
                audit=request.audit,
            )

        latency_ms = round((time.monotonic() - t0) * 1000)
        raw_text = (response.choices[0].message.content or "") if response.choices else ""

        usage = getattr(response, "usage", None)
        input_tokens: Optional[int] = getattr(usage, "prompt_tokens", None)
        output_tokens: Optional[int] = getattr(usage, "completion_tokens", None)
        cost_usd: Optional[float] = (
            _compute_cost(model_id, input_tokens, output_tokens)
            if input_tokens is not None and output_tokens is not None
            else None
        )

        metered_audit = dataclasses.replace(
            request.audit,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
        )

        try:
            parsed = request.response_schema.model_validate_json(raw_text)
        except Exception as exc:  # noqa: BLE001
            return LLMResult(
                parsed=None,
                raw_text=raw_text,
                parse_error=f"schema parse failed: {exc}",
                audit=metered_audit,
            )

        return LLMResult(
            parsed=parsed,
            raw_text=raw_text,
            parse_error=None,
            audit=metered_audit,
        )
