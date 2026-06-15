"""
Tests für sicheren Fallback bei Parse-/Schemafehler (Layer 3, §1.2).
Reine Python-Logik — kein LLM, keine DB.
"""

import uuid

from careapp.domain.validator import FALLBACK_TEXT
from careapp.llm.fallback import (
    fallback_composer_response,
    parse_or_none,
)
from careapp.llm.schemas import ComposerResponse, ScopeSafetyClassification

CV_ID = uuid.UUID("00000000-0000-0000-0000-000000000011")


def test_fallback_uses_exact_wortlaut():
    resp = fallback_composer_response()
    assert len(resp.blocks) == 1
    assert resp.blocks[0].type == "fallback"
    assert resp.blocks[0].text == "Dazu liegen mir keine geprüften Informationen vor."
    # Quelle der Wahrheit ist der Validator-Konstante
    assert resp.blocks[0].text == FALLBACK_TEXT


def test_parse_or_none_success():
    raw = ComposerResponse(blocks=()).model_dump_json()
    parsed, err = parse_or_none(raw, ComposerResponse)
    assert err is None
    assert isinstance(parsed, ComposerResponse)


def test_parse_or_none_invalid_json():
    parsed, err = parse_or_none("{ not valid json", ComposerResponse)
    assert parsed is None
    assert err is not None


def test_parse_or_none_schema_violation():
    """Valides JSON, aber falsches Schema → kein Passthrough."""
    # ScopeSafetyClassification mit fehlenden Pflichtfeldern
    parsed, err = parse_or_none('{"in_scope": true}', ScopeSafetyClassification)
    assert parsed is None
    assert err is not None
    assert "schema validation failed" in err


def test_parse_or_none_extra_field_rejected():
    """Schema-Bruch zur Filter-Umgehung (T11) wird abgewiesen."""
    raw = '{"blocks": [], "smuggled": "freitext"}'
    parsed, err = parse_or_none(raw, ComposerResponse)
    assert parsed is None
    assert err is not None
