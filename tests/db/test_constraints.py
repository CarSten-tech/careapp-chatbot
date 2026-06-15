"""
Tests für DB-Constraints und Trigger (Layer 1, §3.5 + §3.6).
Laufen gegen echte Postgres-Instanz (kein Mock).
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.fixtures.synthetic_heimunterbringung import (
    APPROVAL_CHIEF_ACTOR,
    APPROVAL_EDITOR_ACTOR,
    CLAIM_VERSION_ID,
    SOURCE_PASSAGE_ID,
    SOURCE_VERSION_ID,
    all_objects,
    build_approvals,
    build_claim,
    build_claim_evidence,
    build_claim_version,
    build_source_document,
    build_source_passage,
    build_source_version,
)
from careapp.db.models.claim import Approval, ActorRole, ClaimVersionStatus


_TRUNCATE_ALL = text(
    "TRUNCATE TABLE pathway_branch, pathway_step, decision_node, approval, "
    "scope_assignment, structured_value, claim_evidence, claim_version, claim, "
    "life_situation_pathway, life_situation, source_passage, source_version, "
    "source_document CASCADE;"
)


@pytest.fixture
async def db_with_base_data(session):
    """Lädt alle synthetischen Grunddaten und committet (für Trigger-Tests nötig)."""
    await session.execute(_TRUNCATE_ALL)
    await session.commit()
    for obj in all_objects():
        session.add(obj)
    await session.commit()
    yield session
    await session.execute(_TRUNCATE_ALL)
    await session.commit()


# ------------------------------------------------------------------ #
# Vier-Augen-Prinzip (OD-01)                                          #
# ------------------------------------------------------------------ #

async def test_four_eyes_same_person_rejected(db_with_base_data):
    """chief_editor darf nicht derselbe sein wie der approver."""
    bad_approval = Approval(
        claim_version_id=CLAIM_VERSION_ID,
        actor_id=APPROVAL_EDITOR_ACTOR,
        actor_role=ActorRole.chief_editor,
        action="published",
        at=__import__("datetime").datetime(2024, 2, 1, tzinfo=__import__("datetime").timezone.utc),
        four_eyes_of=APPROVAL_EDITOR_ACTOR,
    )
    db_with_base_data.add(bad_approval)
    with pytest.raises(DBAPIError, match="Four-eyes violation"):
        await db_with_base_data.commit()
    await db_with_base_data.rollback()


async def test_four_eyes_missing_rejected(db_with_base_data):
    """published ohne four_eyes_of wird abgelehnt."""
    bad_approval = Approval(
        claim_version_id=CLAIM_VERSION_ID,
        actor_id=APPROVAL_CHIEF_ACTOR,
        actor_role=ActorRole.chief_editor,
        action="published",
        at=__import__("datetime").datetime(2024, 2, 1, tzinfo=__import__("datetime").timezone.utc),
        four_eyes_of=None,
    )
    db_with_base_data.add(bad_approval)
    with pytest.raises(DBAPIError, match="four_eyes_of must be set"):
        await db_with_base_data.commit()
    await db_with_base_data.rollback()


# ------------------------------------------------------------------ #
# Rollenprüfung (OD-02)                                               #
# ------------------------------------------------------------------ #

async def test_author_cannot_publish(db_with_base_data):
    import datetime
    bad_approval = Approval(
        claim_version_id=CLAIM_VERSION_ID,
        actor_id="author-user",
        actor_role=ActorRole.author,
        action="published",
        at=datetime.datetime(2024, 2, 1, tzinfo=datetime.timezone.utc),
        four_eyes_of=APPROVAL_EDITOR_ACTOR,
    )
    db_with_base_data.add(bad_approval)
    with pytest.raises(DBAPIError, match="Only chief_editor may publish"):
        await db_with_base_data.commit()
    await db_with_base_data.rollback()


async def test_org_admin_cannot_approve(db_with_base_data):
    import datetime
    bad_approval = Approval(
        claim_version_id=CLAIM_VERSION_ID,
        actor_id="admin-user",
        actor_role=ActorRole.org_admin,
        action="approved",
        at=datetime.datetime(2024, 2, 1, tzinfo=datetime.timezone.utc),
        four_eyes_of=None,
    )
    db_with_base_data.add(bad_approval)
    with pytest.raises(DBAPIError, match="Only editor/chief_editor/regional_editor may approve"):
        await db_with_base_data.commit()
    await db_with_base_data.rollback()


# ------------------------------------------------------------------ #
# Unveränderlichkeit ab published (D5)                                #
# ------------------------------------------------------------------ #

async def test_claim_version_statement_immutable_after_published(db_with_base_data):
    """statement_text darf nach published nicht geändert werden."""
    with pytest.raises(DBAPIError, match="immutable once published"):
        await db_with_base_data.execute(
            text("UPDATE claim_version SET statement_text = 'MANIPULIERT' WHERE id = :id"),
            {"id": str(CLAIM_VERSION_ID)},
        )
    await db_with_base_data.rollback()


# ------------------------------------------------------------------ #
# SourceVersion / SourcePassage: append-only                          #
# ------------------------------------------------------------------ #

async def test_source_version_update_rejected(db_with_base_data):
    with pytest.raises(DBAPIError, match="append-only"):
        await db_with_base_data.execute(
            text("UPDATE source_version SET edition_label = 'MANIPULIERT' WHERE id = :id"),
            {"id": str(SOURCE_VERSION_ID)},
        )
    await db_with_base_data.rollback()


async def test_source_passage_update_rejected(db_with_base_data):
    with pytest.raises(DBAPIError, match="append-only"):
        await db_with_base_data.execute(
            text("UPDATE source_passage SET text = 'MANIPULIERT' WHERE id = :id"),
            {"id": str(SOURCE_PASSAGE_ID)},
        )
    await db_with_base_data.rollback()


# ------------------------------------------------------------------ #
# Publish-Voraussetzungen                                             #
# ------------------------------------------------------------------ #

async def test_publish_without_topic_scope_rejected(session):
    """ClaimVersion ohne topic-ScopeAssignment darf nicht published werden (L1-2 / D4)."""
    import datetime, uuid
    doc = build_source_document()
    doc.id = uuid.uuid4()
    doc.canonical_ref = "SGB-XI-SYNTHETIC-NO-TOPIC"
    session.add(doc)
    sv = build_source_version()
    sv.id = uuid.uuid4()
    sv.source_document_id = doc.id
    sv.content_hash = "b" * 64
    session.add(sv)
    sp = build_source_passage()
    sp.id = uuid.uuid4()
    sp.source_version_id = sv.id
    session.add(sp)
    claim = build_claim()
    claim.id = uuid.uuid4()
    session.add(claim)
    cv = build_claim_version()
    cv.id = uuid.uuid4()
    cv.claim_id = claim.id
    cv.status = ClaimVersionStatus.approved
    cv.effective_from = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    cv.published_at = None
    session.add(cv)
    from careapp.db.models.claim import ClaimEvidence, EvidenceRole
    evidence = ClaimEvidence(
        id=uuid.uuid4(),
        claim_version_id=cv.id,
        source_passage_id=sp.id,
        role=EvidenceRole.carrying,
        quote="SYNTHETISCH",
    )
    session.add(evidence)
    # Absichtlich KEIN topic-ScopeAssignment
    await session.flush()
    with pytest.raises(DBAPIError, match="topic ScopeAssignment"):
        await session.execute(
            text("UPDATE claim_version SET status = 'published', published_at = now() WHERE id = :id"),
            {"id": str(cv.id)},
        )
    await session.rollback()


async def test_publish_region_specific_without_region_scope_rejected(session):
    """region_specific ClaimVersion ohne region-ScopeAssignment wird abgelehnt (L1-2 / D4)."""
    import datetime, uuid
    from careapp.db.models.claim import Claim, ClaimEvidence, EvidenceRole, RegionBinding, ScopeAssignment, ScopeDimension
    doc = build_source_document()
    doc.id = uuid.uuid4()
    doc.canonical_ref = "SGB-XI-SYNTHETIC-NO-REGION"
    session.add(doc)
    sv = build_source_version()
    sv.id = uuid.uuid4()
    sv.source_document_id = doc.id
    sv.content_hash = "c" * 64
    session.add(sv)
    sp = build_source_passage()
    sp.id = uuid.uuid4()
    sp.source_version_id = sv.id
    session.add(sp)
    claim = Claim(
        id=uuid.uuid4(),
        topic_scope="stationaere_pflege",
        region_binding=RegionBinding.region_specific,
        created_at=datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc),
    )
    session.add(claim)
    cv = build_claim_version()
    cv.id = uuid.uuid4()
    cv.claim_id = claim.id
    cv.status = ClaimVersionStatus.approved
    cv.effective_from = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    cv.published_at = None
    session.add(cv)
    session.add(ClaimEvidence(
        id=uuid.uuid4(), claim_version_id=cv.id, source_passage_id=sp.id,
        role=EvidenceRole.carrying, quote="SYNTHETISCH",
    ))
    # topic-ScopeAssignment vorhanden, aber KEIN region-ScopeAssignment
    session.add(ScopeAssignment(
        id=uuid.uuid4(), claim_version_id=cv.id,
        dimension=ScopeDimension.topic, value="stationaere_pflege", applies=True,
    ))
    await session.flush()
    with pytest.raises(DBAPIError, match="region ScopeAssignment"):
        await session.execute(
            text("UPDATE claim_version SET status = 'published', published_at = now() WHERE id = :id"),
            {"id": str(cv.id)},
        )
    await session.rollback()


async def test_publish_without_effective_from_rejected(session):
    """ClaimVersion darf ohne effective_from nicht published werden."""
    import datetime, uuid
    doc = build_source_document()
    doc.id = uuid.uuid4()
    doc.canonical_ref = "SGB-XI-SYNTHETIC-NO-DATE"
    session.add(doc)

    sv = build_source_version()
    sv.id = uuid.uuid4()
    sv.source_document_id = doc.id
    session.add(sv)

    sp = build_source_passage()
    sp.id = uuid.uuid4()
    sp.source_version_id = sv.id
    session.add(sp)

    claim = build_claim()
    claim.id = uuid.uuid4()
    session.add(claim)

    cv = build_claim_version()
    cv.id = uuid.uuid4()
    cv.claim_id = claim.id
    cv.status = ClaimVersionStatus.approved
    cv.effective_from = None
    cv.published_at = None
    session.add(cv)

    evidence = build_claim_evidence()
    evidence.id = uuid.uuid4()
    evidence.claim_version_id = cv.id
    evidence.source_passage_id = sp.id
    session.add(evidence)

    await session.flush()

    with pytest.raises(DBAPIError, match="requires effective_from"):
        await session.execute(
            text("UPDATE claim_version SET status = 'published', published_at = now() WHERE id = :id"),
            {"id": str(cv.id)},
        )
    await session.rollback()


# ------------------------------------------------------------------ #
# L1-1: Pathway/Step/Branch/DecisionNode Unveränderlichkeit           #
# ------------------------------------------------------------------ #

async def test_pathway_core_fields_immutable_after_published(db_with_base_data):
    """Kernfelder eines published Pathway dürfen nicht geändert werden (L1-1)."""
    from tests.fixtures.synthetic_heimunterbringung import PATHWAY_ID
    with pytest.raises(DBAPIError, match="immutable once published"):
        await db_with_base_data.execute(
            text("UPDATE life_situation_pathway SET locale = 'en' WHERE id = :id"),
            {"id": str(PATHWAY_ID)},
        )
    await db_with_base_data.rollback()


async def test_pathway_step_update_rejected(db_with_base_data):
    """PathwayStep ist append-only — UPDATE wird abgelehnt (L1-1)."""
    import uuid
    from careapp.db.models.pathway import PathwayStep, DecisionNode, DecisionNodeInputType
    from tests.fixtures.synthetic_heimunterbringung import PATHWAY_ID
    now = __import__("datetime").datetime(2024, 1, 1, tzinfo=__import__("datetime").timezone.utc)
    dn = DecisionNode(
        id=uuid.uuid4(), code="test_step_immutable",
        question_template_de="Testfrage?",
        input_type=DecisionNodeInputType.boolean, options=None, created_at=now,
    )
    db_with_base_data.add(dn)
    await db_with_base_data.flush()
    step = PathwayStep(
        id=uuid.uuid4(), pathway_id=PATHWAY_ID, step_order=99,
        decision_node_id=dn.id, is_required=True, topic_hint=None,
    )
    db_with_base_data.add(step)
    await db_with_base_data.commit()
    with pytest.raises(DBAPIError, match="append-only"):
        await db_with_base_data.execute(
            text("UPDATE pathway_step SET topic_hint = 'MANIPULIERT' WHERE id = :id"),
            {"id": str(step.id)},
        )
    await db_with_base_data.rollback()


async def test_pathway_branch_update_rejected(db_with_base_data):
    """PathwayBranch ist append-only — UPDATE wird abgelehnt (L1-1)."""
    import uuid
    from careapp.db.models.pathway import PathwayStep, PathwayBranch, DecisionNode, DecisionNodeInputType
    from tests.fixtures.synthetic_heimunterbringung import PATHWAY_ID
    now = __import__("datetime").datetime(2024, 1, 1, tzinfo=__import__("datetime").timezone.utc)
    dn = DecisionNode(
        id=uuid.uuid4(), code="test_branch_immutable",
        question_template_de="Testfrage Branch?",
        input_type=DecisionNodeInputType.boolean, options=None, created_at=now,
    )
    db_with_base_data.add(dn)
    await db_with_base_data.flush()
    step = PathwayStep(
        id=uuid.uuid4(), pathway_id=PATHWAY_ID, step_order=98,
        decision_node_id=dn.id, is_required=True, topic_hint=None,
    )
    db_with_base_data.add(step)
    await db_with_base_data.flush()
    branch = PathwayBranch(
        id=uuid.uuid4(), pathway_step_id=step.id,
        answer_value="true", next_step_id=None, retrieval_scope_modifier=None,
    )
    db_with_base_data.add(branch)
    await db_with_base_data.commit()
    with pytest.raises(DBAPIError, match="append-only"):
        await db_with_base_data.execute(
            text("UPDATE pathway_branch SET answer_value = 'MANIPULIERT' WHERE id = :id"),
            {"id": str(branch.id)},
        )
    await db_with_base_data.rollback()


async def test_decision_node_immutable_when_pathway_published(db_with_base_data):
    """DecisionNode-Felder sind eingefroren sobald ein published Pathway ihn verwendet (L1-1)."""
    import uuid
    from careapp.db.models.pathway import PathwayStep, DecisionNode, DecisionNodeInputType
    from tests.fixtures.synthetic_heimunterbringung import PATHWAY_ID
    now = __import__("datetime").datetime(2024, 1, 1, tzinfo=__import__("datetime").timezone.utc)
    dn = DecisionNode(
        id=uuid.uuid4(), code="test_dn_published_lock",
        question_template_de="Wird eingefroren?",
        input_type=DecisionNodeInputType.boolean, options=None, created_at=now,
    )
    db_with_base_data.add(dn)
    await db_with_base_data.flush()
    # Mit published Pathway verknüpfen
    step = PathwayStep(
        id=uuid.uuid4(), pathway_id=PATHWAY_ID, step_order=97,
        decision_node_id=dn.id, is_required=False, topic_hint=None,
    )
    db_with_base_data.add(step)
    await db_with_base_data.commit()
    with pytest.raises(DBAPIError, match="immutable once used in a published Pathway"):
        await db_with_base_data.execute(
            text("UPDATE decision_node SET question_template_de = 'MANIPULIERT' WHERE id = :id"),
            {"id": str(dn.id)},
        )
    await db_with_base_data.rollback()


async def test_decision_node_mutable_before_publish(session):
    """DecisionNode darf geändert werden solange kein published Pathway ihn verwendet (L1-1)."""
    import uuid
    from careapp.db.models.pathway import DecisionNode, DecisionNodeInputType
    now = __import__("datetime").datetime(2024, 1, 1, tzinfo=__import__("datetime").timezone.utc)
    dn = DecisionNode(
        id=uuid.uuid4(), code="test_dn_not_published_yet",
        question_template_de="Darf geändert werden?",
        input_type=DecisionNodeInputType.boolean, options=None, created_at=now,
    )
    session.add(dn)
    await session.commit()
    # Kein published Pathway nutzt diesen Node → Update erlaubt
    await session.execute(
        text("UPDATE decision_node SET question_template_de = 'Geändert.' WHERE id = :id"),
        {"id": str(dn.id)},
    )
    await session.commit()


# ------------------------------------------------------------------ #
# L1-3: SourceVersion content_hash UNIQUE                             #
# ------------------------------------------------------------------ #

async def test_source_version_duplicate_content_hash_rejected(session):
    """Doppelter Import derselben Quelle (gleiche source_document_id + content_hash) wird abgelehnt (L1-3)."""
    import uuid
    doc = build_source_document()
    doc.id = uuid.uuid4()
    doc.canonical_ref = "SGB-XI-SYNTHETIC-HASH-TEST"
    session.add(doc)
    sv1 = build_source_version()
    sv1.id = uuid.uuid4()
    sv1.source_document_id = doc.id
    sv1.content_hash = "d" * 64
    session.add(sv1)
    await session.commit()
    from careapp.db.models.source import SourceVersion
    sv2 = SourceVersion(
        id=uuid.uuid4(),
        source_document_id=doc.id,
        content_hash="d" * 64,  # identischer Hash → Doppel-Import
        edition_label="Duplikat",
        imported_at=__import__("datetime").datetime(2024, 6, 1, tzinfo=__import__("datetime").timezone.utc),
        object_store_uri="s3://synthetic-bucket/duplikat.pdf",
    )
    session.add(sv2)
    with pytest.raises(DBAPIError):
        await session.commit()
    await session.rollback()
