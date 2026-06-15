"""
Synthetische Testdaten für die Pilot-Lebenslage 'heimunterbringung'.
Ausschließlich erfundene Inhalte — keine echten Quellen, keine echten Personen.
Repräsentiert den published-Zustand nach vollständigem redaktionellen Durchlauf.
"""

import uuid
from datetime import datetime, timezone

from careapp.db.models.claim import (
    ActorRole, Approval, Claim, ClaimEvidence, ClaimVersion,
    ClaimVersionStatus, EvidenceRole, RegionBinding, ScopeAssignment, ScopeDimension,
    StructuredValue, StructuredValueKind,
)
from careapp.db.models.pathway import (
    DecisionNode, DecisionNodeInputType, LifeSituation, LifeSituationPathway,
    PathwayBranch, PathwayStatus, PathwayStep,
)
from careapp.db.models.source import SourceDocument, SourcePassage, SourceType, SourceVersion

# Feste UUIDs für reproduzierbare Tests
SOURCE_DOC_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
SOURCE_VERSION_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
SOURCE_PASSAGE_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")
CLAIM_ID = uuid.UUID("00000000-0000-0000-0000-000000000010")
CLAIM_VERSION_ID = uuid.UUID("00000000-0000-0000-0000-000000000011")
LIFE_SITUATION_ID = uuid.UUID("00000000-0000-0000-0000-000000000020")
PATHWAY_ID = uuid.UUID("00000000-0000-0000-0000-000000000021")

EFFECTIVE_FROM = datetime(2024, 1, 1, tzinfo=timezone.utc)
PUBLISHED_AT = datetime(2024, 1, 15, tzinfo=timezone.utc)
APPROVAL_EDITOR_ACTOR = "editor-alice"
APPROVAL_CHIEF_ACTOR = "chief-bob"


def build_source_document() -> SourceDocument:
    return SourceDocument(
        id=SOURCE_DOC_ID,
        type=SourceType.law,
        publisher="Bundesministerium für Gesundheit (SYNTHETISCH)",
        canonical_ref="SGB-XI-SYNTHETIC-2024",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def build_source_version() -> SourceVersion:
    return SourceVersion(
        id=SOURCE_VERSION_ID,
        source_document_id=SOURCE_DOC_ID,
        content_hash="a" * 64,
        edition_label="Synthetische Fassung 2024",
        imported_at=datetime(2024, 1, 10, tzinfo=timezone.utc),
        object_store_uri="s3://synthetic-bucket/sgb-xi-synthetic-2024.pdf",
    )


def build_source_passage() -> SourcePassage:
    return SourcePassage(
        id=SOURCE_PASSAGE_ID,
        source_version_id=SOURCE_VERSION_ID,
        anchor={"section": "§43 SGB XI (SYNTHETISCH)", "page": 1},
        text=(
            "SYNTHETISCHER TEXT: Versicherte haben Anspruch auf Pflege in zugelassenen "
            "Pflegeeinrichtungen (§43 Abs.1 SGB XI – SYNTHETISCH, kein Rechtswert)."
        ),
    )


def build_claim() -> Claim:
    return Claim(
        id=CLAIM_ID,
        topic_scope="stationaere_pflege",
        region_binding=RegionBinding.region_independent,
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def build_claim_version() -> ClaimVersion:
    return ClaimVersion(
        id=CLAIM_VERSION_ID,
        claim_id=CLAIM_ID,
        statement_text=(
            "SYNTHETISCH: Pflegebedürftige Personen haben Anspruch auf vollstationäre Pflege "
            "in einer zugelassenen Pflegeeinrichtung, wenn häusliche oder teilstationäre Pflege "
            "nicht möglich ist oder nicht ausreicht (§43 SGB XI – SYNTHETISCH, kein Rechtswert)."
        ),
        status=ClaimVersionStatus.published,
        effective_from=EFFECTIVE_FROM,
        effective_to=None,
        published_at=PUBLISHED_AT,
        unpublished_at=None,
        tenant_visibility=None,
        conflicting=False,
    )


def build_claim_evidence() -> ClaimEvidence:
    return ClaimEvidence(
        claim_version_id=CLAIM_VERSION_ID,
        source_passage_id=SOURCE_PASSAGE_ID,
        role=EvidenceRole.carrying,
        quote="SYNTHETISCH: Versicherte haben Anspruch auf Pflege in zugelassenen Pflegeeinrichtungen.",
    )


def build_scope_assignments() -> list[ScopeAssignment]:
    return [
        ScopeAssignment(
            claim_version_id=CLAIM_VERSION_ID,
            dimension=ScopeDimension.region,
            value="DE_FEDERAL",
            applies=True,
        ),
        ScopeAssignment(
            claim_version_id=CLAIM_VERSION_ID,
            dimension=ScopeDimension.target_group,
            value="relative",
            applies=True,
        ),
        ScopeAssignment(
            claim_version_id=CLAIM_VERSION_ID,
            dimension=ScopeDimension.target_group,
            value="patient",
            applies=True,
        ),
        ScopeAssignment(
            claim_version_id=CLAIM_VERSION_ID,
            dimension=ScopeDimension.topic,
            value="stationaere_pflege",
            applies=True,
        ),
    ]


def build_structured_value() -> StructuredValue:
    return StructuredValue(
        claim_version_id=CLAIM_VERSION_ID,
        kind=StructuredValueKind.amount_eur,
        value="0",
        unit="EUR",
    )


def build_approvals() -> list[Approval]:
    return [
        Approval(
            claim_version_id=CLAIM_VERSION_ID,
            pathway_id=None,
            actor_id=APPROVAL_EDITOR_ACTOR,
            actor_role=ActorRole.editor,
            action="approved",
            at=datetime(2024, 1, 12, tzinfo=timezone.utc),
            four_eyes_of=None,
        ),
        Approval(
            claim_version_id=CLAIM_VERSION_ID,
            pathway_id=None,
            actor_id=APPROVAL_CHIEF_ACTOR,
            actor_role=ActorRole.chief_editor,
            action="published",
            at=PUBLISHED_AT,
            four_eyes_of=APPROVAL_EDITOR_ACTOR,
        ),
    ]


def build_life_situation() -> LifeSituation:
    from datetime import datetime, timezone
    return LifeSituation(
        id=LIFE_SITUATION_ID,
        code="heimunterbringung",
        label_de="Meine Mutter/mein Vater muss ins Heim",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def build_decision_nodes() -> list[DecisionNode]:
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        DecisionNode(
            code="krankenhaus_aktuell",
            question_template_de="Liegt die betroffene Person gerade im Krankenhaus?",
            input_type=DecisionNodeInputType.boolean,
            options=None,
            created_at=now,
        ),
        DecisionNode(
            code="pflegegrad_vorhanden",
            question_template_de="Hat die betroffene Person bereits einen anerkannten Pflegegrad?",
            input_type=DecisionNodeInputType.boolean,
            options=None,
            created_at=now,
        ),
        DecisionNode(
            code="pflegegrad_stufe",
            question_template_de="Welchen Pflegegrad hat die betroffene Person?",
            input_type=DecisionNodeInputType.enum,
            options={"values": ["1", "2", "3", "4", "5"]},
            created_at=now,
        ),
        DecisionNode(
            code="antrag_gestellt",
            question_template_de="Wurde bereits ein Antrag auf Pflegegrad gestellt?",
            input_type=DecisionNodeInputType.boolean,
            options=None,
            created_at=now,
        ),
    ]


def build_pathway(steps: list[PathwayStep]) -> LifeSituationPathway:
    return LifeSituationPathway(
        id=PATHWAY_ID,
        life_situation_id=LIFE_SITUATION_ID,
        version=1,
        status=PathwayStatus.published,
        published_at=PUBLISHED_AT,
        locale="de",
        description="SYNTHETISCH: Klärungspfad für vollstationäre Heimunterbringung",
    )


def all_objects(
    steps: list[PathwayStep] | None = None,
) -> list:
    """Gibt alle synthetischen Objekte in korrekter Insert-Reihenfolge zurück."""
    nodes = build_decision_nodes()
    life_situation = build_life_situation()
    pathway = LifeSituationPathway(
        id=PATHWAY_ID,
        life_situation_id=LIFE_SITUATION_ID,
        version=1,
        status=PathwayStatus.published,
        published_at=PUBLISHED_AT,
        locale="de",
        description="SYNTHETISCH: Klärungspfad für vollstationäre Heimunterbringung",
    )

    return [
        build_source_document(),
        build_source_version(),
        build_source_passage(),
        build_claim(),
        life_situation,
        pathway,
        build_claim_version(),
        build_claim_evidence(),
        build_structured_value(),
        *build_scope_assignments(),
        *build_approvals(),
        *nodes,
    ]
