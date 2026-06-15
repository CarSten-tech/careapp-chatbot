import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from careapp.db.models.base import Base


class RegionBinding(str, enum.Enum):
    region_independent = "region_independent"
    region_specific = "region_specific"


class ClaimVersionStatus(str, enum.Enum):
    draft = "draft"
    in_review = "in_review"
    approved = "approved"
    published = "published"
    superseded = "superseded"
    withdrawn = "withdrawn"
    expired = "expired"


class EvidenceRole(str, enum.Enum):
    carrying = "carrying"
    supporting = "supporting"
    contextual = "contextual"


class StructuredValueKind(str, enum.Enum):
    amount_eur = "amount_eur"
    deadline_days = "deadline_days"
    date = "date"
    percentage = "percentage"
    count = "count"
    duration_months = "duration_months"


class ScopeDimension(str, enum.Enum):
    region = "region"
    target_group = "target_group"
    topic = "topic"


class ClaimRelationKind(str, enum.Enum):
    supersedes = "supersedes"
    requires = "requires"
    exception_to = "exception_to"
    applies_with = "applies_with"
    conflicts_with = "conflicts_with"


class ActorRole(str, enum.Enum):
    author = "author"
    editor = "editor"
    chief_editor = "chief_editor"
    importer = "importer"
    regional_editor = "regional_editor"
    org_admin = "org_admin"
    system_admin = "system_admin"


class Claim(Base):
    __tablename__ = "claim"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic_scope: Mapped[str] = mapped_column(String(200), nullable=False)
    region_binding: Mapped[RegionBinding] = mapped_column(
        SAEnum(RegionBinding, name="region_binding", create_type=False), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    versions: Mapped[list["ClaimVersion"]] = relationship(back_populates="claim")


class ClaimVersion(Base):
    """
    Core fachliche Aussage-Fassung.
    Kernfelder sind ab status=published unveränderlich (DB-Trigger).
    """

    __tablename__ = "claim_version"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claim.id"), nullable=False)
    statement_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ClaimVersionStatus] = mapped_column(
        SAEnum(ClaimVersionStatus, name="claim_version_status", create_type=False),
        nullable=False,
        default=ClaimVersionStatus.draft,
    )
    effective_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    unpublished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    tenant_visibility: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    conflicting: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    claim: Mapped["Claim"] = relationship(back_populates="versions")
    evidences: Mapped[list["ClaimEvidence"]] = relationship(back_populates="claim_version")
    structured_values: Mapped[list["StructuredValue"]] = relationship(back_populates="claim_version")
    scope_assignments: Mapped[list["ScopeAssignment"]] = relationship(back_populates="claim_version")
    approvals: Mapped[list["Approval"]] = relationship(
        back_populates="claim_version",
        foreign_keys="Approval.claim_version_id",
    )
    outgoing_relations: Mapped[list["ClaimRelation"]] = relationship(
        foreign_keys="ClaimRelation.from_claim_version_id",
        back_populates="from_version",
    )
    incoming_relations: Mapped[list["ClaimRelation"]] = relationship(
        foreign_keys="ClaimRelation.to_claim_version_id",
        back_populates="to_version",
    )


class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claim_version.id"), nullable=False)
    source_passage_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_passage.id"), nullable=False)
    role: Mapped[EvidenceRole] = mapped_column(
        SAEnum(EvidenceRole, name="evidence_role", create_type=False), nullable=False
    )
    quote: Mapped[str] = mapped_column(Text, nullable=False)

    claim_version: Mapped["ClaimVersion"] = relationship(back_populates="evidences")
    passage: Mapped["SourcePassage"] = relationship(  # type: ignore[name-defined]
        "SourcePassage", back_populates="evidences"
    )


class StructuredValue(Base):
    __tablename__ = "structured_value"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claim_version.id"), nullable=False)
    kind: Mapped[StructuredValueKind] = mapped_column(
        SAEnum(StructuredValueKind, name="structured_value_kind", create_type=False), nullable=False
    )
    value: Mapped[str] = mapped_column(String(500), nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    claim_version: Mapped["ClaimVersion"] = relationship(back_populates="structured_values")


class ScopeAssignment(Base):
    __tablename__ = "scope_assignment"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claim_version.id"), nullable=False)
    dimension: Mapped[ScopeDimension] = mapped_column(
        SAEnum(ScopeDimension, name="scope_dimension", create_type=False), nullable=False
    )
    value: Mapped[str] = mapped_column(String(500), nullable=False)
    applies: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    claim_version: Mapped["ClaimVersion"] = relationship(back_populates="scope_assignments")


class ClaimRelation(Base):
    """Append-only (enforced by DB trigger)."""

    __tablename__ = "claim_relation"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_claim_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claim_version.id"), nullable=False)
    to_claim_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claim_version.id"), nullable=False)
    kind: Mapped[ClaimRelationKind] = mapped_column(
        SAEnum(ClaimRelationKind, name="claim_relation_kind", create_type=False), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    from_version: Mapped["ClaimVersion"] = relationship(
        foreign_keys=[from_claim_version_id], back_populates="outgoing_relations"
    )
    to_version: Mapped["ClaimVersion"] = relationship(
        foreign_keys=[to_claim_version_id], back_populates="incoming_relations"
    )


class Approval(Base):
    """Append-only (enforced by DB trigger). Vier-Augen und Rollenprüfung per Trigger."""

    __tablename__ = "approval"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("claim_version.id"), nullable=True
    )
    pathway_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("life_situation_pathway.id"), nullable=True
    )
    actor_id: Mapped[str] = mapped_column(String(200), nullable=False)
    actor_role: Mapped[ActorRole] = mapped_column(
        SAEnum(ActorRole, name="actor_role", create_type=False), nullable=False
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    four_eyes_of: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    claim_version: Mapped[Optional["ClaimVersion"]] = relationship(
        back_populates="approvals", foreign_keys=[claim_version_id]
    )
    pathway: Mapped[Optional["LifeSituationPathway"]] = relationship(  # type: ignore[name-defined]
        "LifeSituationPathway", back_populates="approvals", foreign_keys=[pathway_id]
    )
