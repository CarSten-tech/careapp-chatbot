"""
Citation-API-Tests (Layer 6 §6.1).

Offline-Tests gegen den GET /api/v1/citation/{id} Endpunkt.
DB-Session wird via dependency_overrides durch stubs ersetzt.
"""

import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from careapp.api.app import create_app
from careapp.api.auth import get_auth_context
from careapp.api.deps import get_checkpoint_store, get_db_session, get_llm_client
from careapp.db.models.claim import ClaimVersionStatus, EvidenceRole
from careapp.db.models.source import SourceType
from careapp.llm.port import FakeLLMClient
from careapp.orchestration.checkpoint import InMemoryCheckpointStore
from careapp.orchestration.state import AuthContext

pytestmark = pytest.mark.db

_PILOT_AUTH = AuthContext(
    tenant_id="careapp-pilot",
    region_id="nrw-kreis-neuss",
    target_group_codes=("patient", "family"),
    consent_granted=True,
    locale="de",
)

_CV_ID = uuid.uuid4()


def _make_claim_version(*, status: ClaimVersionStatus, with_evidence: bool = True) -> MagicMock:
    """Baut ein Mock-ClaimVersion-Objekt mit der vollständigen Join-Kette."""
    doc = MagicMock()
    doc.type = SourceType.law
    doc.publisher = "BMAS"
    doc.canonical_ref = "SGB XI §14"

    sv = MagicMock()
    sv.edition_label = "2024-01"
    sv.document = doc

    passage = MagicMock()
    passage.version = sv

    evidence = MagicMock()
    evidence.role = EvidenceRole.carrying
    evidence.quote = "Pflegebedürftig sind Personen, die..."
    evidence.passage = passage

    claim = MagicMock()
    claim.topic_scope = "pflege"

    cv = MagicMock()
    cv.id = _CV_ID
    cv.status = status
    cv.statement_text = "Pflegebedürftigkeit liegt ab Grad 2 vor."
    cv.claim = claim
    cv.evidences = [evidence] if with_evidence else []
    return cv


@asynccontextmanager
async def _session_with(cv: MagicMock | None) -> AsyncGenerator[AsyncSession, None]:
    """Stub-Session die scalar_one_or_none() mit cv antwortet."""
    session = MagicMock(spec=AsyncSession)
    execute_result = MagicMock()
    execute_result.scalar_one_or_none = MagicMock(return_value=cv)
    session.execute = AsyncMock(return_value=execute_result)
    yield session  # type: ignore[misc]


def _make_app(cv: MagicMock | None):
    app = create_app()
    app.dependency_overrides[get_auth_context] = lambda: _PILOT_AUTH
    app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient()
    app.dependency_overrides[get_checkpoint_store] = lambda: InMemoryCheckpointStore()

    async def _session_dep() -> AsyncGenerator[AsyncSession, None]:
        async with _session_with(cv) as s:
            yield s

    app.dependency_overrides[get_db_session] = _session_dep
    return app


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────


async def test_citation_not_found_returns_404():
    """Unbekannte ID → 404."""
    app = _make_app(cv=None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/citation/{uuid.uuid4()}")
    assert r.status_code == 404
    assert r.json()["detail"] == "citation_not_found"


async def test_citation_draft_returns_404():
    """Entwurf (draft) ist nicht abrufbar — §2.3 Vorab-Einsicht verboten."""
    cv = _make_claim_version(status=ClaimVersionStatus.draft)
    app = _make_app(cv=cv)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/citation/{_CV_ID}")
    assert r.status_code == 404


async def test_citation_published_returns_200():
    """Published-ClaimVersion → vollständige CitationResponse."""
    cv = _make_claim_version(status=ClaimVersionStatus.published)
    app = _make_app(cv=cv)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/citation/{_CV_ID}")
    assert r.status_code == 200
    body = r.json()
    assert body["claim_version_id"] == str(_CV_ID)
    assert body["statement_text"] == "Pflegebedürftigkeit liegt ab Grad 2 vor."
    assert body["status"] == "published"
    assert body["topic_scope"] == "pflege"
    assert len(body["evidences"]) == 1
    ev = body["evidences"][0]
    assert ev["role"] == "carrying"
    assert ev["publisher"] == "BMAS"
    assert ev["canonical_ref"] == "SGB XI §14"
    assert ev["source_type"] == "law"
    assert ev["edition_label"] == "2024-01"
    assert "Pflegebedürftig" in ev["quote"]


async def test_citation_no_evidences_returns_empty_list():
    """CV ohne Belegstellen gibt leere evidences-Liste zurück (kein Fehler)."""
    cv = _make_claim_version(status=ClaimVersionStatus.published, with_evidence=False)
    app = _make_app(cv=cv)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/citation/{_CV_ID}")
    assert r.status_code == 200
    assert r.json()["evidences"] == []


async def test_citation_superseded_returns_404():
    """Zurückgezogene/ersetzte Versionen sind nicht abrufbar."""
    cv = _make_claim_version(status=ClaimVersionStatus.superseded)
    app = _make_app(cv=cv)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/api/v1/citation/{_CV_ID}")
    assert r.status_code == 404
