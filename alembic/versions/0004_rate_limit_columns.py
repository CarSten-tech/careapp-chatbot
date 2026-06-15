"""Rate-Limit-Spalten für session_checkpoints (L4-4)

Fügt turns_this_session, max_user_message_chars und max_turns_per_session zur
session_checkpoints-Tabelle hinzu. Bestehende Zeilen erhalten die Defaults:
turns=0, max_chars=2000, max_turns=20 (§8: konkrete Schwellwerte = offene
menschliche Entscheidung — die Enforcement-Schicht ist nun vorhanden).

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-14
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE session_checkpoints
            ADD COLUMN turns_this_session     INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN max_user_message_chars INTEGER NOT NULL DEFAULT 2000,
            ADD COLUMN max_turns_per_session  INTEGER NOT NULL DEFAULT 20
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE session_checkpoints
            DROP COLUMN IF EXISTS turns_this_session,
            DROP COLUMN IF EXISTS max_user_message_chars,
            DROP COLUMN IF EXISTS max_turns_per_session
    """)
