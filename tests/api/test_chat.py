"""
API-Integration-Tests (Layer 6 §6.1).

Getestet gegen die vollständige FastAPI-App (ASGI + httpx.AsyncClient).
Alle Tests sind offline:
  - CAREAPP_DEV_AUTH=true  → Pilot-AuthContext, kein echtes JWT
  - FakeLLMClient          → kein LLM-Aufruf
  - InMemoryCheckpointStore → kein DB für den Store
  - Echter AsyncSession    → DB-Reads für den Orchestrierungs-Kern (gemockt via Override)

Die meisten Tests nutzen den out_of_scope-Pfad (keine DB-Reads im Kern).
DB-gebundene API-Tests (happy path mit echter CV) liegen in tests/db/test_api_integration.py.
"""

import os
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from careapp.api.app import create_app
from careapp.api.auth import get_auth_context
from careapp.api.deps import get_checkpoint_store, get_db_session, get_llm_client
from careapp.llm.port import FakeLLMClient, LLMTouchpoint
from careapp.llm.schemas import ScopeSafetyClassification
from careapp.orchestration.checkpoint import InMemoryCheckpointStore
from careapp.orchestration.state import AuthContext

pytestmark = pytest.mark.db  # nutzt DB (über die async session fixture im conftest)

# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

_PILOT_AUTH = AuthContext(
    tenant_id="careapp-pilot",
    region_id="nrw-kreis-neuss",
    target_group_codes=("patient", "family"),
    consent_granted=True,
    locale="de",
)

_OUT_OF_SCOPE_LLM = FakeLLMClient(
    responses={
        LLMTouchpoint.scope_safety: ScopeSafetyClassification(
            in_scope=False,
            requires_diagnosis_triage_treatment=False,
            requires_individual_eligibility_decision=False,
            safety_signal=False,
            prompt_injection_suspected=False,
            confidence=0.95,
        )
    }
)


@asynccontextmanager
async def _null_session() -> AsyncGenerator[AsyncSession, None]:
    """Stub-Session für Tests die keine DB-Reads im Kern benötigen."""
    # Gibt eine Mock-Session zurück die keine echten SQL-Queries ausführt.
    # Für Tests die nur out_of_scope oder rate_limit testen reicht das,
    # weil der Kern dann vor jedem DB-Zugriff abbricht.
    from unittest.mock import AsyncMock, MagicMock

    session = MagicMock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=MagicMock(mappings=MagicMock(return_value=MagicMock(one_or_none=MagicMock(return_value=None)))))
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    yield session  # type: ignore[misc]


def _make_app(
    *,
    use_null_session: bool = True,
    llm: FakeLLMClient | None = None,
    store: InMemoryCheckpointStore | None = None,
):
    """
    App-Factory für Tests. Überschreibt Dependencies via dependency_overrides.
    """
    app = create_app()
    app.dependency_overrides[get_auth_context] = lambda: _PILOT_AUTH
    app.dependency_overrides[get_llm_client] = lambda: (llm or _OUT_OF_SCOPE_LLM)

    _store = store or InMemoryCheckpointStore()
    app.dependency_overrides[get_checkpoint_store] = lambda: _store

    if use_null_session:
        async def _null_session_dep() -> AsyncGenerator[AsyncSession, None]:
            async with _null_session() as s:
                yield s
        app.dependency_overrides[get_db_session] = _null_session_dep

    return app, _store


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────


async def test_health():
    app, _ = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_chat_out_of_scope_returns_safe_scope():
    """Anfrage außerhalb des Scope → disposition=safe_scope_response."""
    app, _ = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/api/v1/chat", json={"message": "Ich habe Zahnschmerzen."})
    assert r.status_code == 200
    data = r.json()
    assert data["disposition"] == "safe_scope_response"
    assert data["session_id"] is not None
    assert data["turn"] == 1


async def test_chat_returns_session_id_for_continuation():
    """Erste Antwort gibt session_id zurück; zweiter Turn nutzt dieselbe Session."""
    store = InMemoryCheckpointStore()
    app, _ = _make_app(store=store)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r1 = await client.post("/api/v1/chat", json={"message": "Hallo."})
        assert r1.status_code == 200
        session_id = r1.json()["session_id"]

        r2 = await client.post(
            "/api/v1/chat", json={"message": "Noch eine Frage.", "session_id": session_id}
        )
    assert r2.status_code == 200
    assert r2.json()["session_id"] == session_id
    assert r2.json()["turn"] == 2


async def test_chat_message_too_long_returns_no_verified():
    """Nachricht über 2000 Zeichen → L4-4-Guard → no_verified_information."""
    app, _ = _make_app()
    long_message = "x" * 2001
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/api/v1/chat", json={"message": long_message})
    assert r.status_code == 200
    data = r.json()
    assert data["disposition"] == "no_verified_information"
    assert data["fallback_reason"] is not None
    assert "input_too_large" in data["fallback_reason"]


async def test_chat_rate_limit_exceeded_returns_no_verified():
    """Nach 20 Turns → Rate-Limit-Guard → no_verified_information."""
    store = InMemoryCheckpointStore()
    app, _ = _make_app(store=store)

    # 20 Turns ausführen
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        session_id = None
        for i in range(20):
            body = {"message": "Hallo."}
            if session_id:
                body["session_id"] = session_id  # type: ignore[assignment]
            r = await client.post("/api/v1/chat", json=body)
            assert r.status_code == 200
            session_id = r.json()["session_id"]

        # Turn 21 — Rate-Limit
        r21 = await client.post(
            "/api/v1/chat", json={"message": "Noch eine.", "session_id": session_id}
        )
    assert r21.status_code == 200
    data = r21.json()
    assert data["disposition"] == "no_verified_information"
    assert data["fallback_reason"] is not None
    assert "rate_limit_exceeded" in data["fallback_reason"]


async def test_chat_no_consent_returns_safe_scope():
    """Kein Consent → session_start → CONSENT-Node → SafeScopeResponse."""
    app = create_app()
    no_consent_auth = AuthContext(
        tenant_id="careapp-pilot",
        region_id="nrw-kreis-neuss",
        target_group_codes=(),
        consent_granted=False,
        locale="de",
    )
    app.dependency_overrides[get_auth_context] = lambda: no_consent_auth
    app.dependency_overrides[get_llm_client] = lambda: _OUT_OF_SCOPE_LLM
    app.dependency_overrides[get_checkpoint_store] = lambda: InMemoryCheckpointStore()

    async def _null_session_dep() -> AsyncGenerator[AsyncSession, None]:
        async with _null_session() as s:
            yield s
    app.dependency_overrides[get_db_session] = _null_session_dep

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/api/v1/chat", json={"message": "Hallo."})
    assert r.status_code == 200
    assert r.json()["disposition"] == "safe_scope_response"


async def test_get_session_state_after_chat():
    """GET /session/{id}/state gibt turn + clarify_rounds_used zurück."""
    store = InMemoryCheckpointStore()
    app, _ = _make_app(store=store)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/api/v1/chat", json={"message": "Hallo."})
        session_id = r.json()["session_id"]

        rs = await client.get(f"/api/v1/session/{session_id}/state")
    assert rs.status_code == 200
    data = rs.json()
    assert data["session_id"] == session_id
    assert data["turn"] == 1
    assert "clarify_rounds_used" in data


async def test_get_session_state_not_found():
    """Unbekannte session_id → 404."""
    app, _ = _make_app()
    unknown_id = str(uuid.uuid4())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/session/{unknown_id}/state")
    assert r.status_code == 404


async def test_delete_session():
    """DELETE /session/{id} löscht den Checkpoint; danach 404 bei GET."""
    store = InMemoryCheckpointStore()
    app, _ = _make_app(store=store)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Session anlegen
        r = await client.post("/api/v1/chat", json={"message": "Hallo."})
        session_id = r.json()["session_id"]

        # Löschen
        rd = await client.delete(f"/api/v1/session/{session_id}")
        assert rd.status_code == 204

        # Danach weg
        rs = await client.get(f"/api/v1/session/{session_id}/state")
        assert rs.status_code == 404


async def test_chat_blocks_have_normalized_text():
    """Alle Blöcke im Response haben ein `text`-Feld (auch clarifying_question)."""
    app, _ = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/api/v1/chat", json={"message": "Hallo."})
    assert r.status_code == 200
    for block in r.json()["blocks"]:
        assert "text" in block, f"Block ohne text-Feld: {block}"
        assert "type" in block


async def test_openapi_spec_available():
    """OpenAPI-Spec muss generiert und erreichbar sein (Vertrag für Clients)."""
    app, _ = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    assert spec["info"]["title"] == "CareApp Chatbot API"
    assert "/api/v1/chat" in spec["paths"]
    assert "/api/v1/health" in spec["paths"]


async def test_chat_disposition_always_present():
    """disposition ist immer gesetzt — auch bei Fallback-Pfad."""
    app, _ = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/api/v1/chat", json={"message": "x" * 2001})
    data = r.json()
    assert data["disposition"] in {
        "presented",
        "no_verified_information",
        "safe_scope_response",
        "human_handoff",
        "clarify",
        "safety_notice",
    }
