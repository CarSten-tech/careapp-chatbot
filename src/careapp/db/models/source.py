import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from careapp.db.models.base import Base


class SourceType(str, enum.Enum):
    law = "law"
    guideline = "guideline"
    expert_text = "expert_text"
    directory = "directory"


class SourceDocument(Base):
    __tablename__ = "source_document"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[SourceType] = mapped_column(SAEnum(SourceType, name="source_type", create_type=False), nullable=False)
    publisher: Mapped[str] = mapped_column(String(500), nullable=False)
    canonical_ref: Mapped[str] = mapped_column(String(1000), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    versions: Mapped[list["SourceVersion"]] = relationship(back_populates="document")


class SourceVersion(Base):
    """Immutable after insert (enforced by DB trigger)."""

    __tablename__ = "source_version"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_document.id"), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    edition_label: Mapped[str] = mapped_column(String(500), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    object_store_uri: Mapped[str] = mapped_column(String(2000), nullable=False)

    document: Mapped["SourceDocument"] = relationship(back_populates="versions")
    passages: Mapped[list["SourcePassage"]] = relationship(back_populates="version")


class SourcePassage(Base):
    """Immutable after insert (enforced by DB trigger)."""

    __tablename__ = "source_passage"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_version.id"), nullable=False)
    anchor: Mapped[dict] = mapped_column(JSONB, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    version: Mapped["SourceVersion"] = relationship(back_populates="passages")
    evidences: Mapped[list["ClaimEvidence"]] = relationship(  # type: ignore[name-defined]
        "ClaimEvidence", back_populates="passage"
    )
