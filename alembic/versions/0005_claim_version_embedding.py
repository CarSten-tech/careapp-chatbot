"""Hybrid-Retrieval: pgvector-Embedding-Spalte auf claim_version (Layer 2, Recall)

Fügt eine optionale Embedding-Spalte + HNSW-Index hinzu. Die Spalte trägt den
Dense-Vektor je publizierter ClaimVersion für die semantische Recall-Stufe.
Die Erlaubnis (Region/Mandant/Gültigkeit/Status) bleibt unverändert in den
deterministischen Filtern — das Embedding beeinflusst NUR den Recall.

Modell: nvidia/nv-embedqa-e5-v5 → 1024 Dimensionen.

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-16
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

# Dimension des Embedding-Modells (nvidia/nv-embedqa-e5-v5).
EMBED_DIM = 1024


def upgrade() -> None:
    # Einzel-Statements (asyncpg-sicher: kein Mehrfach-Statement pro execute).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.execute(f"ALTER TABLE claim_version ADD COLUMN embedding vector({EMBED_DIM});")
    # HNSW-Index für schnelle Cosine-Nachbarschaftssuche. Indiziert nur Zeilen
    # mit gesetztem Embedding (NULL-Zeilen kosten nichts).
    op.execute(
        "CREATE INDEX ix_claim_version_embedding_hnsw "
        "ON claim_version USING hnsw (embedding vector_cosine_ops);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_claim_version_embedding_hnsw;")
    op.execute("ALTER TABLE claim_version DROP COLUMN IF EXISTS embedding;")
    # Extension bewusst NICHT entfernen — könnte von anderen Objekten genutzt werden.
