"""
API Request/Response-Modelle (Layer 6, §2.2).

Getrennt von den internen Kern-Schemas: Die API-Modelle sind das öffentliche
Vertragsformat (→ OpenAPI-Spec), die Kern-Schemas sind intern.
"""

import uuid
from typing import Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=10_000,  # HTTP-Sicherheitslimit; Business-Limit konfigurierbar via SessionBudgets (L4-4)
        description="Nutzernachricht (Daten, T1)",
    )
    session_id: Optional[uuid.UUID] = Field(
        None, description="Session-ID aus dem vorherigen Turn. Neu bei erstem Turn."
    )


class StructuredValueOut(BaseModel):
    kind: str
    value: str
    unit: Optional[str] = None


class OutputBlockOut(BaseModel):
    """
    Ein Ausgabe-Block der Kern-Antwort. type diskriminiert den Inhalt:
    - empathy: Empathie-Satz, kein Fachinhalt
    - factual_statement: geprüfte Fachaussage mit Quellenangabe
    - clarifying_question: Rückfrage an den Nutzer
    - fallback: Fallback-Wortlaut (keine geprüfte Information verfügbar)
    """

    type: str
    text: str
    claim_version_ids: list[str] = []
    structured_values: list[StructuredValueOut] = []


class ChatResponse(BaseModel):
    session_id: uuid.UUID
    disposition: str = Field(
        description=(
            "presented | no_verified_information | safe_scope_response"
            " | human_handoff | clarify | safety_notice"
        )
    )
    blocks: list[OutputBlockOut]
    audit_ref: Optional[str] = Field(
        None, description="Referenz auf den internen Audit-Trace (für Support/Nachverfolgung)"
    )
    fallback_reason: Optional[str] = Field(
        None, description="Gesetzt wenn kein Ergebnis — enthält den Grund (L4-4, D8, …)"
    )
    turn: int = Field(description="Nummer des Gesprächszugs in dieser Session (ab 1)")


class SessionStateResponse(BaseModel):
    session_id: uuid.UUID
    turn: int
    clarify_rounds_used: int
    pathway_progress: dict[str, str]


class HealthResponse(BaseModel):
    status: str = "ok"


# ------------------------------------------------------------------ #
# Citation                                                            #
# ------------------------------------------------------------------ #


class EvidenceOut(BaseModel):
    """Eine Belegstelle für eine Fachaussage (Zitat aus Quelldokument)."""

    role: str
    quote: str
    source_type: str
    publisher: str
    canonical_ref: str
    edition_label: str


class CitationResponse(BaseModel):
    """
    Vollständige Quellinformation zu einer ClaimVersion.
    Nur für published-Versionen abrufbar (§2.3 — keine Vorab-Einsicht).
    """

    claim_version_id: uuid.UUID
    statement_text: str
    status: str
    topic_scope: str
    evidences: list[EvidenceOut]
