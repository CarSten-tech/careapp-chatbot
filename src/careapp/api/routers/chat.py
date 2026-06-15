"""
Chat-Endpunkte (Layer 6 §2.2).

POST /api/v1/chat         — einen Konversations-Turn ausführen
GET  /api/v1/session/{id}/state — aktuellen Checkpoint lesen (für Reload)
DELETE /api/v1/session/{id}     — Session löschen (Neustart)

Fail-Closed (§7): jede unerwartete Exception landet im Kernel-Fallback,
kein Stack-Trace gelangt zum Client. Die API gibt 200 zurück (Fallback-Antwort)
oder im schlimmsten Fall 503 (Kernel komplett unerreichbar).
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from careapp.api.auth import AuthContextDep
from careapp.api.deps import CheckpointStoreDep, DbSession, GraphConfigDep, LLMClientDep
from careapp.api.models import (
    ChatRequest,
    ChatResponse,
    OutputBlockOut,
    SessionStateResponse,
    StructuredValueOut,
)
from careapp.orchestration.checkpoint import extract_checkpoint
from careapp.orchestration.graph import new_state, run_consultation
from careapp.orchestration.state import SessionBudgets

log = logging.getLogger(__name__)

router = APIRouter()


# ------------------------------------------------------------------ #
# Hilfsfunktionen                                                     #
# ------------------------------------------------------------------ #


def _normalize_block(block: Any) -> OutputBlockOut:
    """
    Konvertiert einen internen OutputBlock in das API-Ausgabeformat.
    ClarifyingQuestionBlock hat `question_text` statt `text` — normalisieren.
    """
    block_type = block.type
    if block_type == "clarifying_question":
        text = getattr(block, "question_text", "")
        return OutputBlockOut(type=block_type, text=text)

    if block_type == "factual_statement":
        svs = [
            StructuredValueOut(kind=sv.kind, value=sv.value, unit=sv.unit)
            for sv in getattr(block, "structured_values", ())
        ]
        return OutputBlockOut(
            type=block_type,
            text=block.text,
            claim_version_ids=[str(cv_id) for cv_id in getattr(block, "claim_version_ids", [])],
            structured_values=svs,
        )

    return OutputBlockOut(type=block_type, text=block.text)


# ------------------------------------------------------------------ #
# POST /chat                                                          #
# ------------------------------------------------------------------ #


@router.post("/chat", response_model=ChatResponse, tags=["chat"])
async def chat(
    body: ChatRequest,
    auth: AuthContextDep,
    session: DbSession,
    llm: LLMClientDep,
    store: CheckpointStoreDep,
    cfg: GraphConfigDep,
) -> ChatResponse:
    """
    Einen Konversations-Turn ausführen.

    Auth-Kontext kommt immer aus dem validierten JWT (T4) — nicht aus dem Body.
    Rate-Limit und Input-Größenlimit werden im Kern (L4-4) geprüft.
    Fail-Closed: auch bei internem Fehler wird eine sichere Fallback-Antwort
    zurückgegeben (Disposition: no_verified_information).
    """
    # Checkpoint laden (None = erster Turn)
    session_id = body.session_id
    cp = await store.load(session_id) if session_id else None

    # State aufbauen — auth kommt aus dem Token (T4)
    state = new_state(
        auth=auth,
        latest_user_message=body.message,
        requested_at=datetime.now(timezone.utc),
        session_id=cp.session_id if cp else session_id,
        clarify_rounds_used=cp.clarify_rounds_used if cp else 0,
        pathway_answers=cp.pathway_answers if cp else {},
        budgets=cp.budgets if cp else SessionBudgets(),
        turns_this_session=cp.turns_this_session if cp else 0,
    )

    # Kern ausführen (immer fail-closed — wirft nie durch)
    state_out = await run_consultation(state, session=session, llm=llm, config=cfg)

    # Checkpoint persistieren
    await store.save(extract_checkpoint(state_out, cfg))

    # Antwort bauen
    blocks: list[OutputBlockOut] = []
    if state_out.final_response:
        blocks = [_normalize_block(b) for b in state_out.final_response.blocks]

    audit_ref = str(state_out.session_id) if state_out.audit else None

    return ChatResponse(
        session_id=state_out.session_id,
        disposition=state_out.disposition.value if state_out.disposition else "no_verified_information",
        blocks=blocks,
        audit_ref=audit_ref,
        fallback_reason=state_out.fallback_reason,
        # extract_checkpoint inkrementiert turns_this_session um 1 → Turn-Nummer entspricht gespeichertem Wert
        turn=state_out.turns_this_session + 1,
    )


# ------------------------------------------------------------------ #
# GET /session/{id}/state                                             #
# ------------------------------------------------------------------ #


@router.get(
    "/session/{session_id}/state",
    response_model=SessionStateResponse,
    tags=["session"],
)
async def get_session_state(
    session_id: uuid.UUID,
    auth: AuthContextDep,
    store: CheckpointStoreDep,
) -> SessionStateResponse:
    """
    Aktuellen Checkpoint einer Session lesen — für Client-seitigen Reload.
    Gibt nur PII-freie Metadaten zurück (analog Checkpoint §5).
    """
    cp = await store.load(session_id)
    if cp is None:
        raise HTTPException(status_code=404, detail="session_not_found")

    return SessionStateResponse(
        session_id=cp.session_id,
        turn=cp.turns_this_session,
        clarify_rounds_used=cp.clarify_rounds_used,
        pathway_progress=dict(cp.pathway_answers),
    )


# ------------------------------------------------------------------ #
# DELETE /session/{id}                                                #
# ------------------------------------------------------------------ #


@router.delete("/session/{session_id}", status_code=204, tags=["session"])
async def delete_session(
    session_id: uuid.UUID,
    auth: AuthContextDep,
    store: CheckpointStoreDep,
) -> None:
    """Löscht den Checkpoint. Der Nutzer startet beim nächsten Chat neu."""
    await store.delete(session_id)
