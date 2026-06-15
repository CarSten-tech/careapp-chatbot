"""
Citation-Endpunkt (Layer 6 §2.3).

GET /api/v1/citation/{claim_version_id}
  Gibt die vollständige Quellinformation für eine ClaimVersion zurück.
  Nur für published-Versionen (§2.3 — keine Vorab-Einsicht in Entwürfe).
  Auth-Kontext erforderlich (T4).
"""

import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from careapp.api.auth import AuthContextDep
from careapp.api.deps import DbSession
from careapp.api.models import CitationResponse, EvidenceOut
from careapp.db.models.claim import ClaimEvidence, ClaimVersion, ClaimVersionStatus
from careapp.db.models.source import SourcePassage, SourceVersion

router = APIRouter()


@router.get(
    "/citation/{claim_version_id}",
    response_model=CitationResponse,
    tags=["citation"],
)
async def get_citation(
    claim_version_id: uuid.UUID,
    auth: AuthContextDep,
    session: DbSession,
) -> CitationResponse:
    """
    Quellinformation zu einer geprüften Fachaussage.

    Die claim_version_id stammt aus dem `claim_version_ids`-Feld eines
    factual_statement-Blocks. Nur published-Versionen sind abrufbar —
    Entwürfe und zurückgezogene Versionen geben 404 zurück.
    """
    result = await session.execute(
        select(ClaimVersion)
        .where(ClaimVersion.id == claim_version_id)
        .options(
            selectinload(ClaimVersion.claim),
            selectinload(ClaimVersion.evidences)
            .selectinload(ClaimEvidence.passage)
            .selectinload(SourcePassage.version)
            .selectinload(SourceVersion.document),
        )
    )
    cv: ClaimVersion | None = result.scalar_one_or_none()

    if cv is None or cv.status != ClaimVersionStatus.published:
        raise HTTPException(status_code=404, detail="citation_not_found")

    evidences = [
        EvidenceOut(
            role=ev.role.value,
            quote=ev.quote,
            source_type=ev.passage.version.document.type.value,
            publisher=ev.passage.version.document.publisher,
            canonical_ref=ev.passage.version.document.canonical_ref,
            edition_label=ev.passage.version.edition_label,
        )
        for ev in cv.evidences
    ]

    return CitationResponse(
        claim_version_id=cv.id,
        statement_text=cv.statement_text,
        status=cv.status.value,
        topic_scope=cv.claim.topic_scope,
        evidences=evidences,
    )
