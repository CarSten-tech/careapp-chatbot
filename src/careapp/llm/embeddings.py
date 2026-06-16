"""
NIM-Embedding-Client für die semantische Recall-Stufe (Hybrid-Retrieval, Layer 2).

Bettet Texte über die OpenAI-kompatible Embeddings-API ein (NVIDIA NIM).
Modell: nvidia/nv-embedqa-e5-v5 → 1024 Dimensionen. Das Modell unterscheidet
zwischen `input_type="passage"` (Wissensbasis-Claims) und `input_type="query"`
(Nutzerfrage) — dieselbe Bedeutung wird je nach Rolle leicht anders eingebettet.

Wichtig (Sicherheits-Invariante): Das Embedding beeinflusst NUR den Recall
(welche Claims als Kandidaten auftauchen) — NIEMALS die Erlaubnis. Ob ein Claim
gezeigt werden darf, entscheiden ausschließlich die deterministischen
Eligibility-Filter (Region/Mandant/Gültigkeit/Status).
"""

from typing import Literal, Optional

DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "nvidia/nv-embedqa-e5-v5"
EMBED_DIM = 1024

InputType = Literal["query", "passage"]


class NIMEmbeddingClient:
    """Dünner Wrapper um die OpenAI-kompatible Embeddings-API (NVIDIA NIM)."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        client: object | None = None,
    ) -> None:
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError(
                    "Das 'openai'-Paket ist nicht installiert (uv sync --extra llm)."
                ) from exc
            client = OpenAI(api_key=api_key, base_url=base_url)
        self._client = client
        self._model = model

    def embed(self, texts: list[str], *, input_type: InputType) -> list[list[float]]:
        """Bettet eine Liste von Texten ein. `input_type` steuert passage vs. query."""
        resp = self._client.embeddings.create(
            model=self._model,
            input=texts,
            extra_body={"input_type": input_type, "truncate": "END"},
        )
        # Reihenfolge der Ausgabe entspricht der Eingabe (per Index sortiert).
        ordered = sorted(resp.data, key=lambda d: d.index)
        return [d.embedding for d in ordered]

    def embed_query(self, text: str) -> list[float]:
        """Bettet eine Nutzerfrage ein (Recall-Seite)."""
        return self.embed([text], input_type="query")[0]

    def embed_passage(self, text: str) -> list[float]:
        """Bettet einen Wissensbasis-Claim ein (Backfill-Seite)."""
        return self.embed([text], input_type="passage")[0]


def embedding_to_pgvector(vec: list[float]) -> str:
    """Serialisiert einen Vektor in das pgvector-Textformat '[v1,v2,...]'."""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"
