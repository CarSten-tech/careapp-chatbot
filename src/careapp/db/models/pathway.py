import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from careapp.db.models.base import Base


class PathwayStatus(str, enum.Enum):
    draft = "draft"
    in_review = "in_review"
    approved = "approved"
    published = "published"
    superseded = "superseded"
    withdrawn = "withdrawn"


class DecisionNodeInputType(str, enum.Enum):
    boolean = "boolean"
    enum = "enum"
    text = "text"


class LifeSituation(Base):
    __tablename__ = "life_situation"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    label_de: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    pathways: Mapped[list["LifeSituationPathway"]] = relationship(back_populates="life_situation")


class LifeSituationPathway(Base):
    """
    Redaktionell freigegebener Gesprächsleitfaden pro Lebenslage.
    Kernfelder ab published unveränderlich (DB-Trigger, gleiche Regel wie ClaimVersion).
    Vier-Augen-Prinzip auf Approval-Tabelle erzwungen.
    """

    __tablename__ = "life_situation_pathway"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    life_situation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("life_situation.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PathwayStatus] = mapped_column(
        SAEnum(PathwayStatus, name="pathway_status"), nullable=False, default=PathwayStatus.draft
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    locale: Mapped[str] = mapped_column(String(10), nullable=False, default="de")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    life_situation: Mapped["LifeSituation"] = relationship(back_populates="pathways")
    steps: Mapped[list["PathwayStep"]] = relationship(
        back_populates="pathway",
        foreign_keys="PathwayStep.pathway_id",
        order_by="PathwayStep.step_order",
    )
    approvals: Mapped[list["Approval"]] = relationship(  # type: ignore[name-defined]
        "Approval",
        back_populates="pathway",
        foreign_keys="Approval.pathway_id",
    )


class DecisionNode(Base):
    """
    Wiederverwendbarer Klärungsbaustein. Einmal erstellt, in mehreren
    Pathways als PathwayStep referenzierbar (D10).
    """

    __tablename__ = "decision_node"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    question_template_de: Mapped[str] = mapped_column(Text, nullable=False)
    input_type: Mapped[DecisionNodeInputType] = mapped_column(
        SAEnum(DecisionNodeInputType, name="decision_node_input_type"), nullable=False
    )
    options: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    pathway_steps: Mapped[list["PathwayStep"]] = relationship(back_populates="decision_node")


class PathwayStep(Base):
    """Ein Schritt (Klärungsfrage) im Pathway. Ab published des Pathway unveränderlich."""

    __tablename__ = "pathway_step"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pathway_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("life_situation_pathway.id"), nullable=False)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    decision_node_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("decision_node.id"), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    topic_hint: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    pathway: Mapped["LifeSituationPathway"] = relationship(
        back_populates="steps", foreign_keys=[pathway_id]
    )
    decision_node: Mapped["DecisionNode"] = relationship(back_populates="pathway_steps")
    branches: Mapped[list["PathwayBranch"]] = relationship(
        foreign_keys="PathwayBranch.pathway_step_id",
        back_populates="step",
    )


class PathwayBranch(Base):
    """Antwort-Zweig: je Antwort-Wert auf den nächsten Schritt (oder Pathway-Ende)."""

    __tablename__ = "pathway_branch"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pathway_step_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pathway_step.id"), nullable=False)
    answer_value: Mapped[str] = mapped_column(String(200), nullable=False)
    next_step_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("pathway_step.id"), nullable=True
    )
    retrieval_scope_modifier: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    step: Mapped["PathwayStep"] = relationship(
        foreign_keys=[pathway_step_id], back_populates="branches"
    )
    next_step: Mapped[Optional["PathwayStep"]] = relationship(foreign_keys=[next_step_id])
