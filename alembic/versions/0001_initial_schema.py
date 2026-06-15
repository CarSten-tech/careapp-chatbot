"""Initial schema: Wissensmodell, Pathways, Trigger (Layer 1)

Revision ID: 0001
Revises:
Create Date: 2026-06-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # ------------------------------------------------------------------ #
    # Enums (idempotent — je ein DO-Block pro op.execute für asyncpg)    #
    # ------------------------------------------------------------------ #
    _enums = [
        ("source_type", "'law','guideline','expert_text','directory'"),
        ("region_binding", "'region_independent','region_specific'"),
        ("claim_version_status", "'draft','in_review','approved','published','superseded','withdrawn','expired'"),
        ("evidence_role", "'carrying','supporting','contextual'"),
        ("structured_value_kind", "'amount_eur','deadline_days','date','percentage','count','duration_months'"),
        ("scope_dimension", "'region','target_group','topic'"),
        ("claim_relation_kind", "'supersedes','requires','exception_to','applies_with','conflicts_with'"),
        ("actor_role", "'author','editor','chief_editor','importer','regional_editor','org_admin','system_admin'"),
        ("pathway_status", "'draft','in_review','approved','published','superseded','withdrawn'"),
        ("decision_node_input_type", "'boolean','enum','text'"),
    ]
    for type_name, labels in _enums:
        op.execute(
            f"DO $$ BEGIN CREATE TYPE {type_name} AS ENUM ({labels});"
            f" EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
        )

    # ------------------------------------------------------------------ #
    # Quell-Entitäten                                                      #
    # ------------------------------------------------------------------ #
    op.create_table(
        "source_document",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("type", sa.Enum(name="source_type", create_type=False), nullable=False),
        sa.Column("publisher", sa.String(500), nullable=False),
        sa.Column("canonical_ref", sa.String(1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("canonical_ref"),
    )

    op.create_table(
        "source_version",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source_document_id", UUID(as_uuid=True), sa.ForeignKey("source_document.id"), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("edition_label", sa.String(500), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("object_store_uri", sa.String(2000), nullable=False),
    )

    op.create_table(
        "source_passage",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source_version_id", UUID(as_uuid=True), sa.ForeignKey("source_version.id"), nullable=False),
        sa.Column("anchor", JSONB, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
    )

    # ------------------------------------------------------------------ #
    # Wissens-Entitäten                                                    #
    # ------------------------------------------------------------------ #
    op.create_table(
        "claim",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("topic_scope", sa.String(200), nullable=False),
        sa.Column("region_binding", sa.Enum(name="region_binding", create_type=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "life_situation",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("label_de", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "life_situation_pathway",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("life_situation_id", UUID(as_uuid=True), sa.ForeignKey("life_situation.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("status", sa.Enum(name="pathway_status", create_type=False), nullable=False, server_default="draft"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locale", sa.String(10), nullable=False, server_default="de"),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
    )

    op.create_table(
        "claim_version",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_id", UUID(as_uuid=True), sa.ForeignKey("claim.id"), nullable=False),
        sa.Column("statement_text", sa.Text, nullable=False),
        sa.Column("status", sa.Enum(name="claim_version_status", create_type=False), nullable=False, server_default="draft"),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unpublished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_visibility", sa.String(200), nullable=True),
        sa.Column("conflicting", sa.Boolean, nullable=False, server_default="false"),
    )

    op.create_table(
        "approval",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_version_id", UUID(as_uuid=True), sa.ForeignKey("claim_version.id"), nullable=True),
        sa.Column("pathway_id", UUID(as_uuid=True), sa.ForeignKey("life_situation_pathway.id"), nullable=True),
        sa.Column("actor_id", sa.String(200), nullable=False),
        sa.Column("actor_role", sa.Enum(name="actor_role", create_type=False), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("four_eyes_of", sa.String(200), nullable=True),
    )

    op.create_table(
        "claim_evidence",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_version_id", UUID(as_uuid=True), sa.ForeignKey("claim_version.id"), nullable=False),
        sa.Column("source_passage_id", UUID(as_uuid=True), sa.ForeignKey("source_passage.id"), nullable=False),
        sa.Column("role", sa.Enum(name="evidence_role", create_type=False), nullable=False),
        sa.Column("quote", sa.Text, nullable=False),
    )

    op.create_table(
        "structured_value",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_version_id", UUID(as_uuid=True), sa.ForeignKey("claim_version.id"), nullable=False),
        sa.Column("kind", sa.Enum(name="structured_value_kind", create_type=False), nullable=False),
        sa.Column("value", sa.String(500), nullable=False),
        sa.Column("unit", sa.String(100), nullable=True),
    )

    op.create_table(
        "scope_assignment",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_version_id", UUID(as_uuid=True), sa.ForeignKey("claim_version.id"), nullable=False),
        sa.Column("dimension", sa.Enum(name="scope_dimension", create_type=False), nullable=False),
        sa.Column("value", sa.String(500), nullable=False),
        sa.Column("applies", sa.Boolean, nullable=False, server_default="true"),
    )

    op.create_table(
        "claim_relation",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("from_claim_version_id", UUID(as_uuid=True), sa.ForeignKey("claim_version.id"), nullable=False),
        sa.Column("to_claim_version_id", UUID(as_uuid=True), sa.ForeignKey("claim_version.id"), nullable=False),
        sa.Column("kind", sa.Enum(name="claim_relation_kind", create_type=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ------------------------------------------------------------------ #
    # Pathway-Entitäten                                                    #
    # ------------------------------------------------------------------ #
    op.create_table(
        "decision_node",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("question_template_de", sa.Text, nullable=False),
        sa.Column("input_type", sa.Enum(name="decision_node_input_type", create_type=False), nullable=False),
        sa.Column("options", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "pathway_step",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("pathway_id", UUID(as_uuid=True), sa.ForeignKey("life_situation_pathway.id"), nullable=False),
        sa.Column("step_order", sa.Integer, nullable=False),
        sa.Column("decision_node_id", UUID(as_uuid=True), sa.ForeignKey("decision_node.id"), nullable=False),
        sa.Column("is_required", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("topic_hint", sa.String(500), nullable=True),
    )

    op.create_table(
        "pathway_branch",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("pathway_step_id", UUID(as_uuid=True), sa.ForeignKey("pathway_step.id"), nullable=False),
        sa.Column("answer_value", sa.String(200), nullable=False),
        sa.Column("next_step_id", UUID(as_uuid=True), sa.ForeignKey("pathway_step.id"), nullable=True),
        sa.Column("retrieval_scope_modifier", JSONB, nullable=True),
    )

    # ------------------------------------------------------------------ #
    # Indizes                                                              #
    # ------------------------------------------------------------------ #
    op.create_index("ix_claim_version_status", "claim_version", ["status"])
    op.create_index("ix_claim_version_claim_id", "claim_version", ["claim_id"])
    op.create_index("ix_scope_assignment_cv", "scope_assignment", ["claim_version_id", "dimension"])
    op.create_index("ix_claim_evidence_cv", "claim_evidence", ["claim_version_id", "role"])
    op.create_index("ix_pathway_step_pathway", "pathway_step", ["pathway_id", "step_order"])
    op.create_index("ix_life_situation_code", "life_situation", ["code"])

    # ------------------------------------------------------------------ #
    # Trigger                                                              #
    # ------------------------------------------------------------------ #
    from careapp.db.triggers import TRIGGER_SQL
    for sql in TRIGGER_SQL:
        op.execute(sql)


def downgrade() -> None:
    from careapp.db.triggers import DROP_TRIGGER_SQL
    for sql in DROP_TRIGGER_SQL:
        op.execute(sql)

    for tbl in [
        "pathway_branch", "pathway_step", "decision_node",
        "claim_relation", "scope_assignment", "structured_value",
        "claim_evidence", "approval", "claim_version", "claim",
        "life_situation_pathway", "life_situation",
        "source_passage", "source_version", "source_document",
    ]:
        op.drop_table(tbl)

    for enum in [
        "source_type", "region_binding", "claim_version_status",
        "evidence_role", "structured_value_kind", "scope_dimension",
        "claim_relation_kind", "actor_role", "pathway_status",
        "decision_node_input_type",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum};")
