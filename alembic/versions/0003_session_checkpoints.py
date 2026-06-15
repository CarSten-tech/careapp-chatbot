"""session_checkpoints-Tabelle für Checkpoint-Persistenz (L4-2 / §5)

Speichert den PII-freien typisierten Gesprächsfortschritt zwischen Turns:
Budget-Zähler, Pathway-Antworten, Versions-Tripel. Kein Freitext, keine PII.
Aufbewahrung / Löschfristen = offene Entscheidung (§8).

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-14
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE session_checkpoints (
            session_id           UUID        PRIMARY KEY,
            clarify_rounds_used  INTEGER     NOT NULL DEFAULT 0,
            -- pathway_answers: decision_node.code → answer_value (typisiert, kein Roh-PII)
            pathway_answers      JSONB       NOT NULL DEFAULT '{}',
            -- SessionBudgets-Felder (damit Session über Turns konsistent bleibt)
            max_clarify_rounds   INTEGER     NOT NULL DEFAULT 2,
            max_recompose        INTEGER     NOT NULL DEFAULT 1,
            max_retrieval_passes INTEGER     NOT NULL DEFAULT 1,
            max_graph_steps      INTEGER     NOT NULL DEFAULT 24,
            -- Versions-Tripel (§1.7 Reproduzierbarkeit + Drift-Erkennung)
            graph_version        TEXT        NOT NULL,
            prompt_set_version   TEXT        NOT NULL,
            model_version        TEXT        NOT NULL,
            -- Timestamps für TTL / Löschfristen (§8)
            created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS session_checkpoints")
