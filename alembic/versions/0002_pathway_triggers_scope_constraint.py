"""Delta: Pathway-Immutability-Trigger, ScopeAssignment-Pflicht-Dimension, content_hash UNIQUE (L1-1, L1-2, L1-3)

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-14
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # L1-2: enforce_published_prerequisites — ScopeAssignment-Checks      #
    # topic ist Pflicht-Dimension (Gate 7 in eligibility.py sonst leer-   #
    # wahr → D4-Verletzung). region ist Pflicht für region_specific Claims.#
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE OR REPLACE FUNCTION enforce_published_prerequisites()
    RETURNS TRIGGER AS $$
    DECLARE
        carrying_count INTEGER;
        scope_count    INTEGER;
        rb             TEXT;
    BEGIN
        IF NEW.status = 'published' AND OLD.status != 'published' THEN
            IF NEW.effective_from IS NULL THEN
                RAISE EXCEPTION
                    'ClaimVersion requires effective_from before publishing (id: %)', NEW.id;
            END IF;

            SELECT COUNT(*) INTO carrying_count
            FROM claim_evidence
            WHERE claim_version_id = NEW.id AND role = 'carrying';
            IF carrying_count = 0 THEN
                RAISE EXCEPTION
                    'ClaimVersion requires at least one carrying evidence before publishing (id: %)', NEW.id;
            END IF;

            SELECT COUNT(*) INTO scope_count
            FROM scope_assignment
            WHERE claim_version_id = NEW.id AND dimension = 'topic' AND applies = true;
            IF scope_count = 0 THEN
                RAISE EXCEPTION
                    'ClaimVersion requires at least one topic ScopeAssignment before publishing (id: %)', NEW.id;
            END IF;

            SELECT c.region_binding INTO rb FROM claim c WHERE c.id = NEW.claim_id;
            IF rb = 'region_specific' THEN
                SELECT COUNT(*) INTO scope_count
                FROM scope_assignment
                WHERE claim_version_id = NEW.id AND dimension = 'region' AND applies = true;
                IF scope_count = 0 THEN
                    RAISE EXCEPTION
                        'Region-specific ClaimVersion requires at least one region ScopeAssignment before publishing (id: %)', NEW.id;
                END IF;
            END IF;
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)

    # ------------------------------------------------------------------ #
    # L1-1: LifeSituationPathway — Kernfelder ab published einfrieren     #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE OR REPLACE FUNCTION enforce_pathway_immutability()
    RETURNS TRIGGER AS $$
    BEGIN
        IF OLD.status IN ('published', 'superseded', 'withdrawn') THEN
            IF (OLD.life_situation_id IS DISTINCT FROM NEW.life_situation_id OR
                OLD.version           IS DISTINCT FROM NEW.version           OR
                OLD.locale            IS DISTINCT FROM NEW.locale) THEN
                RAISE EXCEPTION
                    'LifeSituationPathway core fields are immutable once published (id: %)', OLD.id;
            END IF;
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)
    op.execute("""
    CREATE OR REPLACE TRIGGER pathway_immutability
        BEFORE UPDATE ON life_situation_pathway
        FOR EACH ROW EXECUTE FUNCTION enforce_pathway_immutability();
    """)

    # ------------------------------------------------------------------ #
    # L1-1: PathwayStep und PathwayBranch — append-only                  #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE OR REPLACE TRIGGER pathway_step_append_only
        BEFORE UPDATE OR DELETE ON pathway_step
        FOR EACH ROW EXECUTE FUNCTION deny_modification();
    """)
    op.execute("""
    CREATE OR REPLACE TRIGGER pathway_branch_append_only
        BEFORE UPDATE OR DELETE ON pathway_branch
        FOR EACH ROW EXECUTE FUNCTION deny_modification();
    """)

    # ------------------------------------------------------------------ #
    # L1-1: DecisionNode — Kernfelder einfrieren ab published Pathway     #
    # ------------------------------------------------------------------ #
    op.execute("""
    CREATE OR REPLACE FUNCTION enforce_decision_node_immutability()
    RETURNS TRIGGER AS $$
    DECLARE
        published_count INTEGER;
    BEGIN
        IF (OLD.code                 IS DISTINCT FROM NEW.code                 OR
            OLD.question_template_de IS DISTINCT FROM NEW.question_template_de OR
            OLD.input_type           IS DISTINCT FROM NEW.input_type           OR
            OLD.options              IS DISTINCT FROM NEW.options) THEN
            SELECT COUNT(*) INTO published_count
            FROM pathway_step ps
            JOIN life_situation_pathway lsp ON lsp.id = ps.pathway_id
            WHERE ps.decision_node_id = OLD.id
              AND lsp.status = 'published';
            IF published_count > 0 THEN
                RAISE EXCEPTION
                    'DecisionNode fields are immutable once used in a published Pathway (id: %)', OLD.id;
            END IF;
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)
    op.execute("""
    CREATE OR REPLACE TRIGGER decision_node_immutability
        BEFORE UPDATE ON decision_node
        FOR EACH ROW EXECUTE FUNCTION enforce_decision_node_immutability();
    """)

    # ------------------------------------------------------------------ #
    # L1-3: SourceVersion — kein Doppel-Import desselben Inhalts         #
    # ------------------------------------------------------------------ #
    op.execute("""
    ALTER TABLE source_version
        ADD CONSTRAINT uq_source_version_doc_hash
        UNIQUE (source_document_id, content_hash);
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE source_version DROP CONSTRAINT IF EXISTS uq_source_version_doc_hash;")
    op.execute("DROP TRIGGER IF EXISTS decision_node_immutability ON decision_node;")
    op.execute("DROP FUNCTION IF EXISTS enforce_decision_node_immutability();")
    op.execute("DROP TRIGGER IF EXISTS pathway_branch_append_only ON pathway_branch;")
    op.execute("DROP TRIGGER IF EXISTS pathway_step_append_only ON pathway_step;")
    op.execute("DROP TRIGGER IF EXISTS pathway_immutability ON life_situation_pathway;")
    op.execute("DROP FUNCTION IF EXISTS enforce_pathway_immutability();")
    # enforce_published_prerequisites zurücksetzen (ohne Scope-Checks)
    op.execute("""
    CREATE OR REPLACE FUNCTION enforce_published_prerequisites()
    RETURNS TRIGGER AS $$
    DECLARE
        carrying_count INTEGER;
    BEGIN
        IF NEW.status = 'published' AND OLD.status != 'published' THEN
            IF NEW.effective_from IS NULL THEN
                RAISE EXCEPTION
                    'ClaimVersion requires effective_from before publishing (id: %)', NEW.id;
            END IF;
            SELECT COUNT(*) INTO carrying_count
            FROM claim_evidence
            WHERE claim_version_id = NEW.id AND role = 'carrying';
            IF carrying_count = 0 THEN
                RAISE EXCEPTION
                    'ClaimVersion requires at least one carrying evidence before publishing (id: %)', NEW.id;
            END IF;
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)
