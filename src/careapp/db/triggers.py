"""
DB-Trigger-Definitionen. Werden sowohl in der Alembic-Migration als auch
in der Test-Fixture-Einrichtung verwendet.

TRIGGER_SQL enthält die vollständige Menge aller Trigger (alt + neu).
Migration 0001 importiert diese Liste für Fresh-Installs.
Migration 0002 wendet die Delta-Änderungen (L1-1, L1-2) auf bestehende Instanzen an.
"""

TRIGGER_SQL: list[str] = [
    # ------------------------------------------------------------------ #
    # Hilfsfunktion: Jede Operation außer INSERT ablehnen                 #
    # ------------------------------------------------------------------ #
    """
    CREATE OR REPLACE FUNCTION deny_modification()
    RETURNS TRIGGER AS $$
    BEGIN
        RAISE EXCEPTION 'Table % is append-only: % not allowed', TG_TABLE_NAME, TG_OP;
    END;
    $$ LANGUAGE plpgsql;
    """,

    # ------------------------------------------------------------------ #
    # SourceVersion und SourcePassage: unveränderlich nach Insert         #
    # ------------------------------------------------------------------ #
    """
    CREATE OR REPLACE TRIGGER source_version_immutable
        BEFORE UPDATE OR DELETE ON source_version
        FOR EACH ROW EXECUTE FUNCTION deny_modification();
    """,
    """
    CREATE OR REPLACE TRIGGER source_passage_immutable
        BEFORE UPDATE OR DELETE ON source_passage
        FOR EACH ROW EXECUTE FUNCTION deny_modification();
    """,

    # ------------------------------------------------------------------ #
    # ClaimRelation: append-only                                          #
    # ------------------------------------------------------------------ #
    """
    CREATE OR REPLACE TRIGGER claim_relation_append_only
        BEFORE UPDATE OR DELETE ON claim_relation
        FOR EACH ROW EXECUTE FUNCTION deny_modification();
    """,

    # ------------------------------------------------------------------ #
    # ClaimVersion: Kernfelder ab published einfrieren (D5)               #
    # ------------------------------------------------------------------ #
    """
    CREATE OR REPLACE FUNCTION enforce_claim_version_immutability()
    RETURNS TRIGGER AS $$
    BEGIN
        IF OLD.status IN ('published', 'superseded', 'withdrawn') THEN
            IF (OLD.statement_text IS DISTINCT FROM NEW.statement_text OR
                OLD.claim_id       IS DISTINCT FROM NEW.claim_id       OR
                OLD.effective_from IS DISTINCT FROM NEW.effective_from OR
                OLD.tenant_visibility IS DISTINCT FROM NEW.tenant_visibility) THEN
                RAISE EXCEPTION
                    'ClaimVersion core fields are immutable once published (id: %)', OLD.id;
            END IF;
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """,
    """
    CREATE OR REPLACE TRIGGER claim_version_immutability
        BEFORE UPDATE ON claim_version
        FOR EACH ROW EXECUTE FUNCTION enforce_claim_version_immutability();
    """,

    # ------------------------------------------------------------------ #
    # ClaimVersion: Voraussetzungen beim Übergang nach published prüfen   #
    # L1-2: ScopeAssignment Pflicht-Dimensionen (topic immer, region für  #
    # region_specific Claims). Sonst würde Gate 7/5 in eligibility.py     #
    # bei leerer Scope-Liste leer-wahr — Verletzung von D4.               #
    # ------------------------------------------------------------------ #
    """
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

            -- topic ist Pflicht-Dimension: Gate 7 darf nicht leer sein (D4)
            SELECT COUNT(*) INTO scope_count
            FROM scope_assignment
            WHERE claim_version_id = NEW.id AND dimension = 'topic' AND applies = true;
            IF scope_count = 0 THEN
                RAISE EXCEPTION
                    'ClaimVersion requires at least one topic ScopeAssignment before publishing (id: %)', NEW.id;
            END IF;

            -- region ist Pflicht für region_specific Claims (Gate 5 braucht explizite Zeile)
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
    """,
    """
    CREATE OR REPLACE TRIGGER claim_version_published_prerequisites
        BEFORE UPDATE ON claim_version
        FOR EACH ROW EXECUTE FUNCTION enforce_published_prerequisites();
    """,

    # ------------------------------------------------------------------ #
    # Approval: append-only + Vier-Augen + Rollenprüfung (OD-01, OD-02)  #
    # ------------------------------------------------------------------ #
    """
    CREATE OR REPLACE FUNCTION enforce_approval_rules()
    RETURNS TRIGGER AS $$
    BEGIN
        IF TG_OP IN ('UPDATE', 'DELETE') THEN
            RAISE EXCEPTION 'approval table is append-only';
        END IF;

        IF NEW.action = 'approved' THEN
            IF NEW.actor_role NOT IN ('editor', 'chief_editor', 'regional_editor') THEN
                RAISE EXCEPTION
                    'Only editor/chief_editor/regional_editor may approve (role: %)', NEW.actor_role;
            END IF;
        END IF;

        IF NEW.action = 'published' THEN
            IF NEW.actor_role != 'chief_editor' THEN
                RAISE EXCEPTION
                    'Only chief_editor may publish (role: %)', NEW.actor_role;
            END IF;
            IF NEW.four_eyes_of IS NULL THEN
                RAISE EXCEPTION 'four_eyes_of must be set for published action';
            END IF;
            IF NEW.actor_id = NEW.four_eyes_of THEN
                RAISE EXCEPTION
                    'Four-eyes violation: approver and publisher must be different persons';
            END IF;
        END IF;

        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """,
    """
    CREATE OR REPLACE TRIGGER approval_rules
        BEFORE INSERT OR UPDATE OR DELETE ON approval
        FOR EACH ROW EXECUTE FUNCTION enforce_approval_rules();
    """,

    # ------------------------------------------------------------------ #
    # L1-1: LifeSituationPathway — Kernfelder ab published einfrieren     #
    # Gleiche Regel wie ClaimVersion (D5). Lifecycle-Übergänge (status,   #
    # published_at) bleiben erlaubt; strukturelle Felder nicht.           #
    # ------------------------------------------------------------------ #
    """
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
    """,
    """
    CREATE OR REPLACE TRIGGER pathway_immutability
        BEFORE UPDATE ON life_situation_pathway
        FOR EACH ROW EXECUTE FUNCTION enforce_pathway_immutability();
    """,

    # ------------------------------------------------------------------ #
    # L1-1: PathwayStep und PathwayBranch — append-only                  #
    # Änderung an Schritten/Zweigen eines published Pathway erfordert     #
    # eine neue Pathway-Version — nie direktes UPDATE.                    #
    # ------------------------------------------------------------------ #
    """
    CREATE OR REPLACE TRIGGER pathway_step_append_only
        BEFORE UPDATE OR DELETE ON pathway_step
        FOR EACH ROW EXECUTE FUNCTION deny_modification();
    """,
    """
    CREATE OR REPLACE TRIGGER pathway_branch_append_only
        BEFORE UPDATE OR DELETE ON pathway_branch
        FOR EACH ROW EXECUTE FUNCTION deny_modification();
    """,

    # ------------------------------------------------------------------ #
    # L1-1: DecisionNode — Kernfelder einfrieren sobald ein published     #
    # Pathway diesen Node verwendet (§3.4: "ab published eines nutzenden  #
    # Pathway"). Änderung würde alle nutzenden Pathways unkontrolliert    #
    # beeinflussen.                                                        #
    # ------------------------------------------------------------------ #
    """
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
    """,
    """
    CREATE OR REPLACE TRIGGER decision_node_immutability
        BEFORE UPDATE ON decision_node
        FOR EACH ROW EXECUTE FUNCTION enforce_decision_node_immutability();
    """,
]

DROP_TRIGGER_SQL: list[str] = [
    "DROP TRIGGER IF EXISTS source_version_immutable ON source_version;",
    "DROP TRIGGER IF EXISTS source_passage_immutable ON source_passage;",
    "DROP TRIGGER IF EXISTS claim_relation_append_only ON claim_relation;",
    "DROP TRIGGER IF EXISTS claim_version_immutability ON claim_version;",
    "DROP TRIGGER IF EXISTS claim_version_published_prerequisites ON claim_version;",
    "DROP TRIGGER IF EXISTS approval_rules ON approval;",
    "DROP TRIGGER IF EXISTS pathway_immutability ON life_situation_pathway;",
    "DROP TRIGGER IF EXISTS pathway_step_append_only ON pathway_step;",
    "DROP TRIGGER IF EXISTS pathway_branch_append_only ON pathway_branch;",
    "DROP TRIGGER IF EXISTS decision_node_immutability ON decision_node;",
    "DROP FUNCTION IF EXISTS deny_modification();",
    "DROP FUNCTION IF EXISTS enforce_claim_version_immutability();",
    "DROP FUNCTION IF EXISTS enforce_published_prerequisites();",
    "DROP FUNCTION IF EXISTS enforce_approval_rules();",
    "DROP FUNCTION IF EXISTS enforce_pathway_immutability();",
    "DROP FUNCTION IF EXISTS enforce_decision_node_immutability();",
]
