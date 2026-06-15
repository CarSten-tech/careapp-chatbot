"""
Sicherer Fallback bei Parse-/Schema-Fehler (Layer 3, §1.2).

Eine ungültige LLM-Ausgabe führt NIEMALS zu Freitext-Passthrough und NIEMALS
zu stillem Wiederholen mit gelockerten Regeln. Stattdessen: verbindlicher
Fallback-Block.

Der Fallback-Wortlaut ist die tragende Invariante aus Layer 1/2 und wird hier
aus `careapp.domain.validator` wiederverwendet (eine Quelle der Wahrheit).
"""

from typing import Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from careapp.domain.validator import FALLBACK_TEXT
from careapp.llm.schemas import ComposerResponse, FallbackBlock

T = TypeVar("T", bound=BaseModel)


def fallback_composer_response() -> ComposerResponse:
    """Verbindliche Fallback-Antwort des Composers (exakter Wortlaut)."""
    return ComposerResponse(blocks=(FallbackBlock(text=FALLBACK_TEXT),))


def parse_or_none(raw_text: str, schema: Type[T]) -> tuple[Optional[T], Optional[str]]:
    """
    Validiert Roh-Text strikt gegen ein Schema.

    Rückgabe: (instanz, None) bei Erfolg, (None, fehlertext) bei Parse-/Schemafehler.
    Der Aufrufer geht bei (None, …) auf den sicheren Fallback — kein Passthrough.
    """
    try:
        return schema.model_validate_json(raw_text), None
    except ValidationError as exc:
        return None, f"schema validation failed: {exc.error_count()} error(s)"
    except ValueError as exc:
        return None, f"json parse failed: {exc}"
