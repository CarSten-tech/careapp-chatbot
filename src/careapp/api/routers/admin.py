"""
Admin-Router (Layer 6 — redaktionelles Backend).

Endpunkte (alle unter /api/v1/admin, Bearer-Token-geschützt):

  GET    /admin/stats
  GET    /admin/claims
  POST   /admin/claims
  GET    /admin/claims/{id}
  PATCH  /admin/claims/{id}
  POST   /admin/claims/{id}/transition
  POST   /admin/claims/{id}/approve

  GET    /admin/sources
  POST   /admin/sources
  GET    /admin/sources/{id}/passages
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from careapp.api.auth_admin import require_admin
from careapp.api.deps import get_db_session
from careapp.api.models_admin import (
    AdminStats,
    ApprovalIn,
    ApprovalOut,
    ClaimVersionDetail,
    ClaimVersionListItem,
    CreateClaimIn,
    CreateSourceIn,
    EvidenceOut,
    PassageOut,
    PatchClaimIn,
    ScopeAssignmentOut,
    SourceDocumentOut,
    SourceVersionOut,
    TransitionIn,
)
from careapp.db.models.claim import (
    ActorRole,
    Approval,
    Claim,
    ClaimEvidence,
    ClaimVersion,
    ClaimVersionStatus,
    EvidenceRole,
    RegionBinding,
    ScopeAssignment,
    ScopeDimension,
)
from careapp.db.models.source import (
    SourceDocument,
    SourcePassage,
    SourceType,
    SourceVersion,
)

router = APIRouter(prefix="/admin", tags=["admin"])

AdminDep = Depends(require_admin)
DbSession = AsyncSession


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ #
# Stats                                                               #
# ------------------------------------------------------------------ #


@router.get("/stats", response_model=AdminStats, dependencies=[AdminDep])
async def get_stats(
    session: AsyncSession = Depends(get_db_session),
) -> AdminStats:
    total_cvs_result = await session.execute(select(func.count()).select_from(ClaimVersion))
    total_cvs = total_cvs_result.scalar_one()

    status_rows = await session.execute(
        select(ClaimVersion.status, func.count()).group_by(ClaimVersion.status)
    )
    by_status = {row[0].value: row[1] for row in status_rows}

    total_sources = await session.execute(select(func.count()).select_from(SourceDocument))
    total_passages = await session.execute(select(func.count()).select_from(SourcePassage))

    return AdminStats(
        claims_total=total_cvs,
        claims_by_status=by_status,
        sources_total=total_sources.scalar_one(),
        passages_total=total_passages.scalar_one(),
    )


# ------------------------------------------------------------------ #
# ClaimVersion — List + Create                                        #
# ------------------------------------------------------------------ #


@router.get("/claims", response_model=list[ClaimVersionListItem], dependencies=[AdminDep])
async def list_claims(
    status: str | None = None,
    topic: str | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> list[ClaimVersionListItem]:
    stmt = (
        select(ClaimVersion)
        .join(Claim, ClaimVersion.claim_id == Claim.id)
        .options(selectinload(ClaimVersion.approvals))
        .order_by(Claim.created_at.desc())
    )
    if status:
        try:
            stmt = stmt.where(ClaimVersion.status == ClaimVersionStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Ungültiger Status: {status}")
    if topic:
        stmt = stmt.where(Claim.topic_scope.ilike(f"%{topic}%"))

    result = await session.execute(stmt)
    cvs = result.scalars().all()

    items = []
    for cv in cvs:
        claim = await session.get(Claim, cv.claim_id)
        items.append(
            ClaimVersionListItem(
                id=cv.id,
                claim_id=cv.claim_id,
                statement_text=cv.statement_text,
                status=cv.status.value,
                topic_scope=claim.topic_scope if claim else "",
                region_binding=claim.region_binding.value if claim else "",
                approvals_count=len(cv.approvals),
                created_at=claim.created_at if claim else _now(),
            )
        )
    return items


@router.post("/claims", response_model=ClaimVersionDetail, status_code=201, dependencies=[AdminDep])
async def create_claim(
    body: CreateClaimIn,
    session: AsyncSession = Depends(get_db_session),
) -> ClaimVersionDetail:
    try:
        rb = RegionBinding(body.region_binding)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Ungültiges region_binding: {body.region_binding}")

    now = _now()

    claim = Claim(id=uuid.uuid4(), topic_scope=body.topic_scope, region_binding=rb, created_at=now)
    session.add(claim)
    await session.flush()

    cv = ClaimVersion(
        id=uuid.uuid4(),
        claim_id=claim.id,
        statement_text=body.statement_text,
        status=ClaimVersionStatus.draft,
    )
    session.add(cv)
    await session.flush()

    for sa_in in body.scope_assignments:
        try:
            dim = ScopeDimension(sa_in.dimension)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Ungültige Dimension: {sa_in.dimension}")
        session.add(
            ScopeAssignment(
                id=uuid.uuid4(),
                claim_version_id=cv.id,
                dimension=dim,
                value=sa_in.value,
                applies=sa_in.applies,
            )
        )

    if body.evidence:
        passage = await session.get(SourcePassage, body.evidence.source_passage_id)
        if not passage:
            raise HTTPException(status_code=404, detail="source_passage_not_found")
        try:
            role = EvidenceRole(body.evidence.role)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Ungültige Evidence-Rolle: {body.evidence.role}")
        session.add(
            ClaimEvidence(
                id=uuid.uuid4(),
                claim_version_id=cv.id,
                source_passage_id=passage.id,
                role=role,
                quote=body.evidence.quote,
            )
        )

    await session.commit()
    return await _load_cv_detail(session, cv.id)


# ------------------------------------------------------------------ #
# ClaimVersion — Detail + Patch                                       #
# ------------------------------------------------------------------ #


@router.get("/claims/{cv_id}", response_model=ClaimVersionDetail, dependencies=[AdminDep])
async def get_claim(
    cv_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> ClaimVersionDetail:
    return await _load_cv_detail(session, cv_id)


@router.patch("/claims/{cv_id}", response_model=ClaimVersionDetail, dependencies=[AdminDep])
async def patch_claim(
    cv_id: uuid.UUID,
    body: PatchClaimIn,
    session: AsyncSession = Depends(get_db_session),
) -> ClaimVersionDetail:
    cv = await session.get(ClaimVersion, cv_id)
    if not cv:
        raise HTTPException(status_code=404, detail="claim_version_not_found")
    if cv.status != ClaimVersionStatus.draft:
        raise HTTPException(status_code=409, detail="Nur Entwürfe (draft) können bearbeitet werden")
    if body.statement_text is not None:
        cv.statement_text = body.statement_text
    await session.commit()
    return await _load_cv_detail(session, cv_id)


# ------------------------------------------------------------------ #
# Status-Transition                                                   #
# ------------------------------------------------------------------ #

_VALID_TRANSITIONS: dict[ClaimVersionStatus, set[ClaimVersionStatus]] = {
    ClaimVersionStatus.draft: {ClaimVersionStatus.in_review, ClaimVersionStatus.withdrawn},
    ClaimVersionStatus.in_review: {
        ClaimVersionStatus.draft,
        ClaimVersionStatus.approved,
        ClaimVersionStatus.withdrawn,
    },
    ClaimVersionStatus.approved: {
        ClaimVersionStatus.in_review,
        ClaimVersionStatus.published,
        ClaimVersionStatus.withdrawn,
    },
    ClaimVersionStatus.published: {ClaimVersionStatus.superseded, ClaimVersionStatus.withdrawn},
    ClaimVersionStatus.superseded: set(),
    ClaimVersionStatus.withdrawn: set(),
    ClaimVersionStatus.expired: set(),
}


@router.post("/claims/{cv_id}/transition", response_model=ClaimVersionDetail, dependencies=[AdminDep])
async def transition_claim(
    cv_id: uuid.UUID,
    body: TransitionIn,
    session: AsyncSession = Depends(get_db_session),
) -> ClaimVersionDetail:
    cv = await session.get(ClaimVersion, cv_id)
    if not cv:
        raise HTTPException(status_code=404, detail="claim_version_not_found")

    try:
        target = ClaimVersionStatus(body.target_status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Ungültiger Status: {body.target_status}")

    allowed = _VALID_TRANSITIONS.get(cv.status, set())
    if target not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Statusübergang {cv.status.value} → {target.value} nicht erlaubt",
        )

    cv.status = target
    if target == ClaimVersionStatus.published:
        cv.published_at = _now()
    elif target in {ClaimVersionStatus.withdrawn, ClaimVersionStatus.superseded}:
        cv.unpublished_at = _now()

    await session.commit()
    return await _load_cv_detail(session, cv_id)


# ------------------------------------------------------------------ #
# Approval                                                            #
# ------------------------------------------------------------------ #


@router.post("/claims/{cv_id}/approve", response_model=ClaimVersionDetail, dependencies=[AdminDep])
async def add_approval(
    cv_id: uuid.UUID,
    body: ApprovalIn,
    session: AsyncSession = Depends(get_db_session),
) -> ClaimVersionDetail:
    cv = await session.get(ClaimVersion, cv_id)
    if not cv:
        raise HTTPException(status_code=404, detail="claim_version_not_found")

    try:
        role = ActorRole(body.actor_role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Ungültige Rolle: {body.actor_role}")

    if body.action not in {"approve", "publish", "reject"}:
        raise HTTPException(status_code=400, detail=f"Ungültige Aktion: {body.action}")

    session.add(
        Approval(
            id=uuid.uuid4(),
            claim_version_id=cv.id,
            actor_id=body.actor_id,
            actor_role=role,
            action=body.action,
            at=_now(),
            four_eyes_of=body.four_eyes_of,
        )
    )

    # Automatischer Statusübergang durch Freigabe
    if body.action == "approve" and cv.status == ClaimVersionStatus.in_review:
        cv.status = ClaimVersionStatus.approved
    elif body.action == "publish" and cv.status == ClaimVersionStatus.approved:
        cv.status = ClaimVersionStatus.published
        cv.published_at = _now()
    elif body.action == "reject":
        cv.status = ClaimVersionStatus.draft

    await session.commit()
    return await _load_cv_detail(session, cv_id)


# ------------------------------------------------------------------ #
# Source Documents                                                    #
# ------------------------------------------------------------------ #


@router.get("/sources", response_model=list[SourceDocumentOut], dependencies=[AdminDep])
async def list_sources(
    session: AsyncSession = Depends(get_db_session),
) -> list[SourceDocumentOut]:
    result = await session.execute(
        select(SourceDocument)
        .options(
            selectinload(SourceDocument.versions).selectinload(SourceVersion.passages)
        )
        .order_by(SourceDocument.created_at.desc())
    )
    docs = result.scalars().all()
    return [_source_to_out(doc) for doc in docs]


@router.post("/sources", response_model=SourceDocumentOut, status_code=201, dependencies=[AdminDep])
async def create_source(
    body: CreateSourceIn,
    session: AsyncSession = Depends(get_db_session),
) -> SourceDocumentOut:
    try:
        st = SourceType(body.type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Ungültiger Typ: {body.type}")

    now = _now()

    doc = SourceDocument(
        id=uuid.uuid4(),
        type=st,
        publisher=body.publisher,
        canonical_ref=body.canonical_ref,
        created_at=now,
    )
    session.add(doc)
    await session.flush()

    import hashlib

    content = "\n".join(p.text for p in body.passages)
    content_hash = hashlib.sha256(content.encode()).hexdigest()

    version = SourceVersion(
        id=uuid.uuid4(),
        source_document_id=doc.id,
        content_hash=content_hash,
        edition_label=body.edition_label,
        imported_at=now,
        object_store_uri=body.object_store_uri or f"manual://{doc.id}",
    )
    session.add(version)
    await session.flush()

    for p_in in body.passages:
        session.add(
            SourcePassage(
                id=uuid.uuid4(),
                source_version_id=version.id,
                anchor=p_in.anchor,
                text=p_in.text,
            )
        )

    await session.commit()

    result = await session.execute(
        select(SourceDocument)
        .where(SourceDocument.id == doc.id)
        .options(selectinload(SourceDocument.versions).selectinload(SourceVersion.passages))
    )
    return _source_to_out(result.scalar_one())


@router.get("/sources/{doc_id}/passages", response_model=list[PassageOut], dependencies=[AdminDep])
async def list_passages(
    doc_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> list[PassageOut]:
    doc = await session.get(SourceDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="source_document_not_found")

    result = await session.execute(
        select(SourcePassage)
        .join(SourceVersion, SourcePassage.source_version_id == SourceVersion.id)
        .where(SourceVersion.source_document_id == doc_id)
        .order_by(SourcePassage.id)
    )
    passages = result.scalars().all()
    return [PassageOut(id=p.id, anchor=p.anchor, text=p.text) for p in passages]


# ------------------------------------------------------------------ #
# Helper                                                              #
# ------------------------------------------------------------------ #


async def _load_cv_detail(session: AsyncSession, cv_id: uuid.UUID) -> ClaimVersionDetail:
    result = await session.execute(
        select(ClaimVersion)
        .where(ClaimVersion.id == cv_id)
        .options(
            selectinload(ClaimVersion.scope_assignments),
            selectinload(ClaimVersion.evidences),
            selectinload(ClaimVersion.approvals),
        )
    )
    cv = result.scalar_one_or_none()
    if not cv:
        raise HTTPException(status_code=404, detail="claim_version_not_found")

    claim = await session.get(Claim, cv.claim_id)

    return ClaimVersionDetail(
        id=cv.id,
        claim_id=cv.claim_id,
        statement_text=cv.statement_text,
        status=cv.status.value,
        topic_scope=claim.topic_scope if claim else "",
        region_binding=claim.region_binding.value if claim else "",
        effective_from=cv.effective_from,
        effective_to=cv.effective_to,
        published_at=cv.published_at,
        scope_assignments=[
            ScopeAssignmentOut(id=sa.id, dimension=sa.dimension.value, value=sa.value, applies=sa.applies)
            for sa in cv.scope_assignments
        ],
        evidences=[
            EvidenceOut(
                id=e.id,
                source_passage_id=e.source_passage_id,
                role=e.role.value,
                quote=e.quote,
            )
            for e in cv.evidences
        ],
        approvals=[
            ApprovalOut(
                id=a.id,
                actor_id=a.actor_id,
                actor_role=a.actor_role.value,
                action=a.action,
                at=a.at,
                four_eyes_of=a.four_eyes_of,
            )
            for a in sorted(cv.approvals, key=lambda a: a.at)
        ],
    )


def _source_to_out(doc: SourceDocument) -> SourceDocumentOut:
    return SourceDocumentOut(
        id=doc.id,
        type=doc.type.value,
        publisher=doc.publisher,
        canonical_ref=doc.canonical_ref,
        created_at=doc.created_at,
        versions=[
            SourceVersionOut(
                id=v.id,
                edition_label=v.edition_label,
                imported_at=v.imported_at,
                passages_count=len(v.passages),
            )
            for v in doc.versions
        ],
    )
