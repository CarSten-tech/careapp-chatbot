"""
Pydantic-Modelle für das Admin-API (Layer 6).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ------------------------------------------------------------------ #
# Scope                                                               #
# ------------------------------------------------------------------ #


class ScopeAssignmentIn(BaseModel):
    dimension: str  # "topic" | "region" | "target_group"
    value: str
    applies: bool = True


class ScopeAssignmentOut(BaseModel):
    id: uuid.UUID
    dimension: str
    value: str
    applies: bool


# ------------------------------------------------------------------ #
# Evidence                                                            #
# ------------------------------------------------------------------ #


class EvidenceIn(BaseModel):
    source_passage_id: uuid.UUID
    role: str = "carrying"
    quote: str


class EvidenceOut(BaseModel):
    id: uuid.UUID
    source_passage_id: uuid.UUID
    role: str
    quote: str


# ------------------------------------------------------------------ #
# Approval                                                            #
# ------------------------------------------------------------------ #


class ApprovalIn(BaseModel):
    actor_id: str = Field(..., min_length=1, max_length=200)
    actor_role: str  # "editor" | "chief_editor"
    action: str  # "approve" | "publish"
    four_eyes_of: Optional[str] = None


class ApprovalOut(BaseModel):
    id: uuid.UUID
    actor_id: str
    actor_role: str
    action: str
    at: datetime
    four_eyes_of: Optional[str]


# ------------------------------------------------------------------ #
# ClaimVersion                                                        #
# ------------------------------------------------------------------ #


class CreateClaimIn(BaseModel):
    statement_text: str = Field(..., min_length=10)
    topic_scope: str = Field(..., min_length=1, max_length=200)
    region_binding: str = "region_independent"
    scope_assignments: list[ScopeAssignmentIn] = Field(default_factory=list)
    evidence: Optional[EvidenceIn] = None


class PatchClaimIn(BaseModel):
    statement_text: Optional[str] = Field(None, min_length=10)


class TransitionIn(BaseModel):
    target_status: str  # in_review | approved | published | withdrawn | superseded


class ClaimVersionListItem(BaseModel):
    id: uuid.UUID
    claim_id: uuid.UUID
    statement_text: str
    status: str
    topic_scope: str
    region_binding: str
    approvals_count: int
    created_at: datetime


class ClaimVersionDetail(BaseModel):
    id: uuid.UUID
    claim_id: uuid.UUID
    statement_text: str
    status: str
    topic_scope: str
    region_binding: str
    effective_from: Optional[datetime]
    effective_to: Optional[datetime]
    published_at: Optional[datetime]
    scope_assignments: list[ScopeAssignmentOut]
    evidences: list[EvidenceOut]
    approvals: list[ApprovalOut]


# ------------------------------------------------------------------ #
# Source                                                              #
# ------------------------------------------------------------------ #


class PassageIn(BaseModel):
    anchor: dict
    text: str = Field(..., min_length=1)


class CreateSourceIn(BaseModel):
    type: str  # "law" | "guideline" | "expert_text" | "directory"
    publisher: str = Field(..., min_length=1, max_length=500)
    canonical_ref: str = Field(..., min_length=1, max_length=1000)
    edition_label: str = Field(..., min_length=1, max_length=500)
    object_store_uri: str = ""
    passages: list[PassageIn] = Field(default_factory=list)


class PassageOut(BaseModel):
    id: uuid.UUID
    anchor: dict
    text: str


class SourceVersionOut(BaseModel):
    id: uuid.UUID
    edition_label: str
    imported_at: datetime
    passages_count: int


class SourceDocumentOut(BaseModel):
    id: uuid.UUID
    type: str
    publisher: str
    canonical_ref: str
    created_at: datetime
    versions: list[SourceVersionOut]


# ------------------------------------------------------------------ #
# Dashboard                                                           #
# ------------------------------------------------------------------ #


class AdminStats(BaseModel):
    claims_total: int
    claims_by_status: dict[str, int]
    sources_total: int
    passages_total: int
