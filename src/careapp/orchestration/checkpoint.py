"""
Checkpoint-Persistenz (Layer 4 §5 / L4-2).

`SessionCheckpoint` speichert den minimalen **typisierten** Fortschritt
eines Gesprächs über Turns hinweg — PII-frei (§5):
  - kein latest_user_message (Freitext)
  - kein Auth-Kontext (kommt vom Auth-System, nicht aus dem Checkpoint)
  - kein confirmed_facts (könnte Gesprächsinhalt mit PII tragen)

`CheckpointStore` ist ein Protocol (port-basiert, analog LLMClient §6).
Implementierungen:
  - `InMemoryCheckpointStore`    — für Tests und lokale Entwicklung
  - `SupabaseCheckpointStore`    — produktiv, SQLAlchemy + PostgreSQL UPSERT

`extract_checkpoint(state, cfg)` extrahiert den Checkpoint aus einem
abgeschlossenen Turn-State. Der Aufrufer persistiert und lädt:

    cp = await store.load(session_id)
    state = new_state(...,
        session_id=cp.session_id,
        clarify_rounds_used=cp.clarify_rounds_used,
        pathway_answers=cp.pathway_answers,
        budgets=cp.budgets,
    )
    state = await run_consultation(state, ...)
    await store.save(extract_checkpoint(state, cfg))
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Protocol, runtime_checkable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from careapp.orchestration.state import (
    ConsultationState,
    GraphConfig,
    GraphVersionTriple,
    SessionBudgets,
)


# ------------------------------------------------------------------ #
# Checkpoint-Datenstruktur (PII-frei)                                 #
# ------------------------------------------------------------------ #


@dataclass(frozen=True)
class SessionCheckpoint:
    """
    Minimaler PII-freier Fortschritt eines Gesprächs (§5).

    Felder absichtlich NICHT enthalten:
    - latest_user_message  (Freitext)
    - auth                 (kommt vom Auth-System)
    - confirmed_facts      (könnte Gesprächsinhalt mit PII tragen)
    - trace / llm_audits   (ephemer, Layer-6-Telemetrie — nicht im Checkpoint)
    """

    session_id: uuid.UUID
    clarify_rounds_used: int
    pathway_answers: dict[str, str]  # decision_node.code → answer_value (typisiert, kein Roh-PII)
    budgets: SessionBudgets
    versions: GraphVersionTriple     # §1.7: Versions-Tripel für Reproduzierbarkeit + Drift-Erkennung
    turns_this_session: int = 0      # L4-4: nach jedem Turn um 1 erhöht (extract_checkpoint)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ------------------------------------------------------------------ #
# Store-Protocol                                                      #
# ------------------------------------------------------------------ #


@runtime_checkable
class CheckpointStore(Protocol):
    """Port für Checkpoint-Persistenz. Analog LLMClient (§6): anbieter-agnostisch."""

    async def save(self, checkpoint: SessionCheckpoint) -> None:
        """Speichert oder aktualisiert den Checkpoint (UPSERT nach session_id)."""
        ...

    async def load(self, session_id: uuid.UUID) -> Optional[SessionCheckpoint]:
        """Lädt den Checkpoint; `None` wenn die Session unbekannt ist."""
        ...

    async def delete(self, session_id: uuid.UUID) -> None:
        """Löscht den Checkpoint. No-op wenn session_id unbekannt."""
        ...


# ------------------------------------------------------------------ #
# In-Memory-Implementierung (Tests / lokale Entwicklung)              #
# ------------------------------------------------------------------ #


class InMemoryCheckpointStore:
    """Thread-unsicher, nicht persistent — ausschließlich für Tests und REPL."""

    def __init__(self) -> None:
        self._store: dict[uuid.UUID, SessionCheckpoint] = {}

    async def save(self, checkpoint: SessionCheckpoint) -> None:
        updated = SessionCheckpoint(
            session_id=checkpoint.session_id,
            clarify_rounds_used=checkpoint.clarify_rounds_used,
            pathway_answers=dict(checkpoint.pathway_answers),
            budgets=checkpoint.budgets,
            versions=checkpoint.versions,
            turns_this_session=checkpoint.turns_this_session,
            created_at=self._store[checkpoint.session_id].created_at
            if checkpoint.session_id in self._store
            else checkpoint.created_at,
            updated_at=datetime.now(timezone.utc),
        )
        self._store[checkpoint.session_id] = updated

    async def load(self, session_id: uuid.UUID) -> Optional[SessionCheckpoint]:
        return self._store.get(session_id)

    async def delete(self, session_id: uuid.UUID) -> None:
        self._store.pop(session_id, None)


# ------------------------------------------------------------------ #
# Supabase / PostgreSQL-Implementierung                               #
# ------------------------------------------------------------------ #


class SupabaseCheckpointStore:
    """
    Persistenter Store gegen PostgreSQL (Supabase). Verwendet UPSERT
    (INSERT … ON CONFLICT DO UPDATE) — idempotent und multi-turn-sicher.

    Aufbewahrung / Löschfristen sind konfigurierbar (§8, offene Entscheidung).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, checkpoint: SessionCheckpoint) -> None:
        await self._session.execute(
            text("""
                INSERT INTO session_checkpoints
                    (session_id, clarify_rounds_used, pathway_answers,
                     max_clarify_rounds, max_recompose, max_retrieval_passes, max_graph_steps,
                     max_user_message_chars, max_turns_per_session,
                     turns_this_session,
                     graph_version, prompt_set_version, model_version,
                     created_at, updated_at)
                VALUES
                    (:session_id, :clarify_rounds_used, CAST(:pathway_answers AS JSONB),
                     :max_clarify_rounds, :max_recompose, :max_retrieval_passes, :max_graph_steps,
                     :max_user_message_chars, :max_turns_per_session,
                     :turns_this_session,
                     :graph_version, :prompt_set_version, :model_version,
                     :created_at, :updated_at)
                ON CONFLICT (session_id) DO UPDATE SET
                    clarify_rounds_used    = EXCLUDED.clarify_rounds_used,
                    pathway_answers        = EXCLUDED.pathway_answers,
                    max_clarify_rounds     = EXCLUDED.max_clarify_rounds,
                    max_recompose          = EXCLUDED.max_recompose,
                    max_retrieval_passes   = EXCLUDED.max_retrieval_passes,
                    max_graph_steps        = EXCLUDED.max_graph_steps,
                    max_user_message_chars = EXCLUDED.max_user_message_chars,
                    max_turns_per_session  = EXCLUDED.max_turns_per_session,
                    turns_this_session     = EXCLUDED.turns_this_session,
                    graph_version          = EXCLUDED.graph_version,
                    prompt_set_version     = EXCLUDED.prompt_set_version,
                    model_version          = EXCLUDED.model_version,
                    updated_at             = EXCLUDED.updated_at
            """),
            {
                "session_id": str(checkpoint.session_id),
                "clarify_rounds_used": checkpoint.clarify_rounds_used,
                "pathway_answers": json.dumps(checkpoint.pathway_answers),
                "max_clarify_rounds": checkpoint.budgets.max_clarify_rounds,
                "max_recompose": checkpoint.budgets.max_recompose,
                "max_retrieval_passes": checkpoint.budgets.max_retrieval_passes,
                "max_graph_steps": checkpoint.budgets.max_graph_steps,
                "max_user_message_chars": checkpoint.budgets.max_user_message_chars,
                "max_turns_per_session": checkpoint.budgets.max_turns_per_session,
                "turns_this_session": checkpoint.turns_this_session,
                "graph_version": checkpoint.versions.graph_version,
                "prompt_set_version": checkpoint.versions.prompt_set_version,
                "model_version": checkpoint.versions.model_version,
                "created_at": checkpoint.created_at,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        await self._session.commit()

    async def delete(self, session_id: uuid.UUID) -> None:
        await self._session.execute(
            text("DELETE FROM session_checkpoints WHERE session_id = :sid"),
            {"sid": str(session_id)},
        )
        await self._session.commit()

    async def load(self, session_id: uuid.UUID) -> Optional[SessionCheckpoint]:
        row = (
            await self._session.execute(
                text("SELECT * FROM session_checkpoints WHERE session_id = :sid"),
                {"sid": str(session_id)},
            )
        ).mappings().one_or_none()

        if row is None:
            return None

        return SessionCheckpoint(
            session_id=uuid.UUID(str(row["session_id"])),
            clarify_rounds_used=row["clarify_rounds_used"],
            pathway_answers=dict(row["pathway_answers"]),
            budgets=SessionBudgets(
                max_clarify_rounds=row["max_clarify_rounds"],
                max_recompose=row["max_recompose"],
                max_retrieval_passes=row["max_retrieval_passes"],
                max_graph_steps=row["max_graph_steps"],
                max_user_message_chars=row["max_user_message_chars"],
                max_turns_per_session=row["max_turns_per_session"],
            ),
            versions=GraphVersionTriple(
                graph_version=row["graph_version"],
                prompt_set_version=row["prompt_set_version"],
                model_version=row["model_version"],
            ),
            turns_this_session=row["turns_this_session"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


# ------------------------------------------------------------------ #
# Helfer                                                              #
# ------------------------------------------------------------------ #


def extract_checkpoint(state: ConsultationState, cfg: GraphConfig) -> SessionCheckpoint:
    """
    Extrahiert den PII-freien Checkpoint aus einem abgeschlossenen Turn-State.
    Aufrufen nach `run_consultation`, vor dem nächsten `new_state`.

    `turns_this_session` wird um 1 erhöht — L4-4: der nächste Turn liest den
    aktualisierten Zähler und prüft ihn gegen `max_turns_per_session`.
    """
    return SessionCheckpoint(
        session_id=state.session_id,
        clarify_rounds_used=state.clarify_rounds_used,
        pathway_answers=dict(state.pathway_answers),
        budgets=state.budgets,
        versions=cfg.versions,
        turns_this_session=state.turns_this_session + 1,
    )
