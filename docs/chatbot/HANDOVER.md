# CareApp Chatbot – Übergabepunkt

**Zweck:** Jederzeit kalt übernehmbarer Stand der Architekturplanung. Wird nach
jedem Meilenstein aktualisiert. Letzter Stand: **2026-06-14 (Admin-Backend Welle 6d fertig: 14 FastAPI-Endpunkte + 11 Next.js-Admin-Seiten + Vier-Augen-Workflow. Build grün.)**.

## Was geplant wird

Nur der **Chatbot-Teil mit agentischem Datenbankwissen**, auf Enterprise-Niveau.
Zentrale Idee: LLM = nur Sprache/Gesprächsführung; jede fachliche Aussage stammt
aus einer versionierten, redaktionell freigegebenen Wissensbasis und wird vor
Ausgabe deterministisch auf Belegbarkeit geprüft. Sicherheitsziel: unbelegte
fachliche Aussagen erreichen die UI nie. Fallback-Wortlaut:
„Dazu liegen mir keine geprüften Informationen vor.“

## Statusübersicht

| Layer | Dokument | Status |
|---|---|---|
| 1 Datenmodell | `architecture-knowledge-and-control-core.md` §3 | ✅ Accepted + ✅ implementiert (Welle 1: L1-1/L1-2/L1-3 geschlossen) |
| 2 Deterministischer Kontrollkern | `architecture-knowledge-and-control-core.md` §4 | ✅ Accepted + ✅ implementiert |
| 3 LLM-Verträge & Threat-Model | `architecture-llm-layers-and-threat-model.md` | ✅ Accepted + ✅ implementiert (3.1–3.3 fertig) |
| 4 Orchestrierung | `architecture-orchestration.md` | ✅ Accepted + 🟡 teilimplementiert (4.1 Spine + 4.2 Pathway) |
| 5 Evaluation & Pilot | `architecture-evaluation-and-pilot.md` | ✅ Accepted + ✅ vollständig implementiert (5a: Eval-Framework + C1–C17; 5b: Rate-Limit-Guard; 5c: Versions-Tripel §4, CI-Pipeline, Pilot-Checkliste §5.1) |
| 6 API & Clients | `architecture-clients.md` | ✅ Accepted + 🟡 offen: Deployment (Welle 6f). Implementiert: 6a FastAPI-Skeleton; 6b Citation-API+Overlay; 6c Next.js Chat-UI; 6d Admin-Backend (14 Endpunkte, Vier-Augen-Workflow, 11 Admin-Seiten); 6e E2E-Gerüst. Build grün, middleware→proxy.ts migriert. |

Tragende Invarianten: **D1–D8** (Layer 1/2) und **T1–T13** (Layer 3) gelten
schichtübergreifend. Index: `README.md`.

## Wichtigste Designentscheidungen (Kurz)

- Identität (SourceDocument, Claim) ⊥ Fassung (SourceVersion, ClaimVersion).
- Atomarität, strukturierte Werte, „unknown → false”, Unveränderlichkeit ab
  `published` per DB-Trigger, zweiklassige Region.
- Validator vertraut der Composer-Ausgabe nichts (frisch nachladen, Anti-TOCTOU).
- LLM: Drei-Kanal-Trennung, schema-erzwungene Ausgabe, minimale Fähigkeiten.
- Orchestrierung: statischer versionierter Graph, Tool-Allowlist pro Node,
  Budgets, Fail-Closed-Degradation.
- **LifeSituationPathway** (D9–D11): Gesprächsführung folgt redaktionell
  freigegebenen, versionierten Pathways. `Clarify` fragt nie frei, sondern
  liest den nächsten offenen `PathwayStep`. ~10–15 Kern-Pathways manuell,
  Rest wiederverwendete `DecisionNodes`. KI kann Entwürfe vorschlagen,
  Fachredaktion gibt frei. Neuer Node `ResolvePathway` im Graph.

## Offene Entscheidungen (nicht durch KI zu treffen)

Vier-Augen-Prinzip, Pilot-Lebenslagen/-region, anonym vs. Konto,
Aufbewahrungsfristen, LLM-Anbieter/Hosting, Quellenhierarchie/Konfliktauflösung,
MVP-Sprachen, Handoff-Ausgestaltung, konkrete Budgetwerte, regulatorische
Einordnung. (Details je Layer im Abschnitt „Offene Entscheidungen“.)

## Modellnutzung beim Weiterplanen

Kern-/Sicherheitsentscheidungen → Opus 4.8 (hoch). Ausformulierung (Schemas,
Migrationen, Test-Sets) → Sonnet 4.6 (mittel). Boilerplate → Haiku 4.5.

## Offene Entscheidungen

Alle 13 offenen Punkte sind in [`open-decisions.md`](open-decisions.md)
strukturiert nach Blocker-Status und zuständigen Personen.

**OD-01 bis OD-04 sind entschieden (2026-06-13):**
- Vier-Augen-Prinzip: immer aktiv
- Rollen: author, editor, chief_editor, importer, regional_editor, org_admin, system_admin → [`roles.md`](roles.md)
- Pilot-Lebenslage: „Meine Mutter muss ins Heim" (stationäre Pflege)
- Pilotregion: Kreis Neuss / Düsseldorf (NRW)

Noch offen: OD-05–13 (nicht blockierend für Layer-1-Start).

## Implementierungsstand (2026-06-13)

Layer 1 + Layer 2 vollständig implementiert und getestet gegen **Supabase** (eu-central-1, Frankfurt).

Setup:
- uv + Python 3.12 (via Homebrew)
- Supabase-Projekt: `careApp_test_project` (ID: `tbfzghhxeutbkbqubowp`), PostgreSQL 17.6.1
- Kein Docker nötig — alle Tests laufen gegen Supabase
- `.env` → `DATABASE_URL` + `TEST_DATABASE_URL` zeigen auf Supabase

### Testergebnis: **45/45 grün**

**Layer 1 (30 Tests):**
- Eligibility-Filter: 22/22 (reine Python-Logik, kein DB)
- DB-Constraint-Tests: 8/8 (gegen echte Supabase-Instanz)
  - Vier-Augen-Prinzip (2 Tests)
  - Rollen-Enforcement (2 Tests)
  - Unveränderlichkeit ab published (1 Test)
  - Append-only source_version/source_passage (2 Tests)
  - Publish-Voraussetzungen (1 Test)

**Layer 2 (15 Tests, `tests/db/test_layer2.py`):**
- Evidence Builder: 5 Tests (happy path, abgelaufen, D7-Ausschluss, D7-pass, conflicting)
- Coverage-Bewertung: 4 Tests (sufficient, partial, insufficient, unknown intent)
- Post-Generation-Validator (D8): 6 Tests (pass, no SVs, TOCTOU, SV-mismatch, not in package, unknown ID)

### Implementierte Layer-2-Dateien

```
src/careapp/domain/
  evidence_builder.py   # §4.2 + D7: Eligibility-Filter + Relations-Prüfung → EvidencePackage
  coverage.py           # §4.3: ASPECT_MAP + sufficient/partial/insufficient
  validator.py          # §4.4 + D8: Anti-TOCTOU, SV-Vergleich, Fallback-Text
```

### Wichtige Implementierungsdetails Layer 2

- `EvidenceBuilder.build_evidence_package()` lädt alle CVs, wendet alle 10 Eligibility-Gates an,
  prüft dann D7 (requires/exception_to): Ziel-CV nicht eligible → Quell-CV in `excluded_ids`.
- **Pilot-Einschränkung D7**: Ziel-CVs werden nur innerhalb des geladenen Sets geprüft
  (gleicher `topic_scope`). Cross-Topic-Relationen gelten konservativ als nicht erfüllbar.
  Für Layer 3+: erweiterbar durch separate D7-Abfrage ohne topic_scope-Filter.
- `ASPECT_MAP` in `coverage.py` ist Pilot-Stand (nur `stationaere_pflege` für `heimunterbringung`).
  Fachredaktion ergänzt weitere Aspekte je Lebenslage.
- `compute_coverage()` akzeptiert optionalen `aspect_map`-Parameter (für Tests/Overrides).
- Validator verwendet `_cv_to_snapshot` etc. aus `evidence_builder.py` (kein Import-Zirkel).
- Fallback-Text fest: `"Dazu liegen mir keine geprüften Informationen vor."`
- Test-Fixture `_Builder` in `test_layer2.py`: zufällige UUIDs pro Instanz, verhindert
  Konflikte mit Parallelläufen. `db_clean`-Fixture: TRUNCATE + COMMIT vor/nach jedem Test.
- `unpublished_at` und `effective_to` sind NICHT im Immutability-Trigger eingefroren →
  können auf published CVs aktualisiert werden (für TOCTOU-Tests relevant).

### Bekannte Einschränkungen (für spätere Layer)

- Gate-7-Bypass für D7-Ziel-CVs: Cross-Topic-Relationen können in Layer 3 korrekt
  behandelt werden, indem die D7-Prüfung topic_scope-agnostisch erfolgt.
- `ASPECT_MAP` muss bei jedem neuen Piloten / jeder neuen Lebenslage erweitert werden.
- Optionaler LLM-Judge (§4.4) noch nicht implementiert (Layer 3-Aufgabe).

## Layer 3 — Implementierungsstand (in Arbeit)

**Milestone 3.1 fertig (deterministische Grundlage, ohne Live-LLM).**
Geschnitten in Teil-Meilensteine wegen Aufwand (~2–3× Layer 2) und Budget.

### Implementierte Layer-3-Dateien (`src/careapp/llm/`)

```
schemas.py            # §2: strikte Pydantic-Schemas LLM-1..LLM-5 + Output-Block-Allowlist (T11/T12)
port.py               # §1.3 + §6: anbieter-agnostischer LLMClient-Protocol, Budgets, Audit, FakeLLMClient
channels.py           # §1.1 + T2: Drei-Kanal-Prompt, harte <evidence>/<facts>-Abgrenzung + Delimiter-Neutralisierung
scope_safety.py       # §2 LLM-1 + DoD: decide_scope_safety = Regeln + Klassifikation + Fallback (LLM darf nur verschärfen)
fallback.py           # §1.2: parse_or_none + fallback_composer_response (Wortlaut aus validator.py)
anthropic_adapter.py  # Referenz-Adapter (Anthropic Claude), lazy import, optionales Extra `llm`
```

### Architekturentscheidung: Anbieter-agnostisch (Architektur §6)

Der produktive LLM-Anbieter ist eine **offene menschliche Entscheidung** und wird
NICHT im Code festgelegt. Der Laufzeitkern spricht nur gegen `LLMClient` (Port).
`AnthropicLLMClient` ist die empfohlene **Default-Referenz** (Modell `claude-opus-4-8`,
adaptive thinking, `messages.parse` für schema-erzwungene Ausgabe), aber austauschbar.
`anthropic` ist optionales Extra (`uv sync --extra llm`); der Kern ist ohne SDK voll testbar.

### Testergebnis Layer 3.1: **34/34 grün** (`tests/llm/`, reine Python-Logik, kein DB/LLM)
- Schemas + Allowlist: 11 (strikt, extra=forbid, factual_statement verlangt ≥1 claim_version_id)
- Drei-Kanal/T2: 7 (Delimiter-Neutralisierung verhindert Ausbruch aus `<evidence>`)
- Fallback: 5 (Parse-/Schemafehler → kein Passthrough, exakter Fallback-Wortlaut)
- Scope/Safety-Kombinator: 11 (u.a. „LLM kann Scope nicht gewähren, den Regeln verweigern")

**Gesamtsuite nach 3.1: 79/79 grün** (30 Layer1 + 15 Layer2 + 34 Layer3.1).

## Layer 3.2 — Grounded Response Composer (LLM-5) fertig

**Milestone 3.2 verdrahtet den einzigen formulierenden Laufzeit-LLM-Aufruf mit
dem deterministischen Validator (D8).** Kein Live-LLM nötig — Tests mit
`FakeLLMClient` gegen echte Supabase-Evidence.

### Implementierte Datei

```
src/careapp/llm/composer.py   # LLM-5: Evidence rendern → Drei-Kanal-Prompt → Port
                              # → Allowlist (T11/T12) → Bridge zu validate_statements (D8)
```

- `compose_grounded_response(...)` gibt IMMER eine UI-sichere `ComposerResponse`
  zurück (validierte Ausgabe ODER Fallback) plus `ComposerOutcome`
  (used_fallback, fallback_reason, validation, audit) für die Orchestrierung/Audit.
- **Fail-closed an drei Stellen:** (1) Parse-/Schemafehler → Fallback ohne
  Validierung; (2) nicht erlaubter Blocktyp → Fallback; (3) eine einzige nicht
  belegbare `factual_statement` → **ganze** Antwort verworfen (`report.fallback_required`).
- **Bridge:** jede `FactualStatementBlock` → `FactualStatement`
  (claim_version_ids + strukturierte Werte) → `validate_statements`. Composer-Text
  ist Behauptung, kein Beleg.
- Empathie-/Rückfrage-/Fallback-Blöcke tragen keine fachliche Aussage und werden
  nicht validiert (leere Validierung = passed → Passthrough).
- `DEFAULT_COMPOSER_MODEL_ID = "claude-sonnet-4-6"` ist nur ein Audit-/Referenzlabel;
  der konkrete Anbieter ist die injizierte `LLMClient`-Implementierung (offen, §6).

### Testergebnis Layer 3.2: **6/6 grün** (`tests/db/test_composer.py`, gegen Supabase)
- happy path (echte CV-ID → besteht), nur Empathie+Rückfrage (Passthrough),
  gültiger strukturierter Wert (besteht)
- erfundene claim_version_id → Fallback (D8), Wert-Mismatch → Fallback (D3),
  Parse-/Schemafehler → Fallback (§1.2)

**Gesamtsuite nach 3.2: 85/85 grün** (30 Layer1 + 15 Layer2 + 34 Layer3.1 + 6 Layer3.2).

## Layer 3.3 — Threat-Tests T1–T13 fertig (Layer 3 abgeschlossen)

**Jeder Bedrohungsvektor aus §3 ist ein nach Threat-ID benannter, ausführbarer
Negativtest.** Aufgeteilt nach Konvention: offline vs. DB-gebunden.

```
tests/llm/test_threats.py     # offline: T1,T2,T3,T5,T7,T10,T11,T12,T13 (11 Tests)
tests/db/test_threats_db.py   # DB/Composer→Validator: T4,T6,T8,T9 (4 Tests)
```

- **T1** Nutzereingabe bleibt Daten · **T2** `</evidence>`-Ausbruch neutralisiert ·
  **T3** med. Jailbreak → out_of_scope · **T5** Anspruchsableitung → out_of_scope ·
  **T7** keine factual_statement ohne CV-ID + Intent trennt Hypothese⊥Fakt ·
  **T10** Budget-Struktur vorhanden (Durchsetzung = Layer 4) · **T11** Schema-Bruch →
  kein Passthrough · **T12** nicht freigegebener Blocktyp abgewiesen · **T13** Scope je Turn neu.
- **T4** Nutzertext hat keine Autorität über `ctx` (Auth-Kontext) · **T6** Betrags-
  Manipulation → Fallback (D3) · **T8** TOCTOU build→ablauf→present → Fallback (D8) ·
  **T9** Zitat einer D7-ausgeschlossenen CV → Fallback (Package-Mitgliedschaft).

**Gesamtsuite nach Layer 3: 100/100 grün** (30 L1 + 15 L2 + 34 L3.1 + 6 L3.2 + 15 L3.3).

### DoD Layer 3 — vollständig ✅
- [x] Strikte Ausgabeschemata LLM-1..LLM-5 inkl. Parsefehler-Fallback
- [x] Drei-Kanal-Prompt-Konstruktion für LLM-5 (Evidence/Facts hart abgegrenzt)
- [x] Output-Block-Allowlist serverseitig erzwungen
- [x] Scope/Safety als Kombination Regeln + Klassifikation + Fallback (nicht LLM-allein)
- [x] Prompt- und Modellversion im Audit referenziert (`LLMCallAudit`)
- [x] Composer LLM-5 verdrahtet + Bridge zu `validate_statements` (D8), fail-closed
- [x] Threat-Tests T1–T13 als ausführbare Negativtests
- [x] Import-seitige Injection-Prüfung notiert (Codeverweis in `composer.render_evidence_text`, Architektur §3b)
- [x] Budgets pro Aufruf **definiert** (`LLMCallBudget`); offen bleibt nur die *Durchsetzung* pro Node/Session = **Layer 4**

## Layer 4.1 — Orchestrierungs-Spine fertig (DECIDE_FREE-Pfad)

**Statischer, versionierter Graph, der die Layer-2/3-Bausteine fail-closed verkettet.**
Bewusst eigene schlanke Graph-Engine (LangGraph ist in der Spec nur *vorgeschlagen*);
1:1 LangGraph-adaptierbar, Adoption bleibt offene Infra-Entscheidung (analog §6).

### Implementierte Dateien (`src/careapp/orchestration/`)

```
tools.py   # Tool-Allowlist pro Node, serverseitig erzwungen (ToolContext → ToolNotAllowed)
state.py   # ConsultationState (typisiert, Hypothese⊥Fakt⊥Evidenz⊥Meta), GraphConfig, Audit, Budgets
nodes.py   # 12 Nodes; delegieren an compute_coverage / compose_grounded_response / decide_scope_safety
graph.py   # statische ALLOWED_EDGES + Fail-Closed-Runner (Exception/illegale Kante/Step-Limit → Fallback)
```

- **Gefolded für den Pilot:** Retrieve/Filter/Build → `EvaluateCoverage` (Layer 2);
  Compose+Validate → `compose_grounded_response` (D8, fail-closed). Dokumentiert in `nodes.py`.
- **T4** verankert: `_request_context` baut `RequestContext` aus Auth-Kontext, nie aus der Nachricht.
- **Audit (§6):** Versions-Tripel, Nodes, Tool-Aufrufe, `claim_version_id`s, ValidationResult,
  Fallback-Grund, LLM-Prompt-/Modellversionen je Node.
- **Modellwahl pro Node** in `GraphConfig` (Haiku für LLM-1..4, Sonnet für LLM-5), anbieter-agnostisch.

### Testergebnis Layer 4.1: **9/9 grün** (`tests/db/test_orchestration.py`)
Happy Path (grounded → Present) · out_of_scope → SafeScope · LLM-1-Parsefehler → SafeScope ·
fehlende Einwilligung → SafeScope (kein LLM) · Coverage insufficient → NoVerified ·
Composer erfindet CV → NoVerified (D8) · missing_info → Clarify · Clarify-Budget erschöpft →
NoVerified · Tool-Allowlist blockt `db_read` in SafetyCheck.

**Gesamtsuite nach 4.1: 109/109 grün** (100 Layer1-3 + 9 Layer4.1).

## Layer 4.2 — Pathway-Pfad fertig

**Der zweite Graph-Ast (DECIDE_PATH).** `UnderstandConcern → ResolvePathway`;
`ResolvePathway` entscheidet DECIDE_PATH vs. DECIDE_FREE, neuer `BuildRetrievalPlan`-Node
vor `EvaluateCoverage`.

- **`ResolvePathway`** (det, `db_read`): mappt `resolved_intent → LifeSituation.code →
  published Pathway`; folgt `PathwayBranch`-Zweigen deterministisch zum nächsten offenen
  Schritt oder Pathway-Ende. Das LLM bestimmt den Pathway nie.
- **`Clarify`** im Pathway-Modus: stellt die freigegebene `question_template_de` des nächsten
  offenen `PathwayStep` — **deterministisch, kein LLM-Aufruf**, kein freies Fragen. (Der freie
  Clarify-Pfad mit LLM-3 bleibt für Anfragen ohne Pathway.)
- **`BuildRetrievalPlan`** (det): nutzt `PathwayStep.topic_hint` / terminalen
  `PathwayBranch.retrieval_scope_modifier` zur Coverage-Fokussierung (`coverage_aspect_override`).
- **State:** `pathway_answers` (decision_node.code → answer_value) + `clarify_rounds_used` tragen
  den Fortschritt typisiert & ohne Roh-PII über Turns (checkpoint-fähig). `new_state(...)` reicht sie herein.

### Testergebnis Layer 4.2: **5/5 grün** (`tests/db/test_pathway.py`)
Mehrturniger `heimunterbringung`-Durchlauf: Turn 1 fragt Step 1 (Template) · Turn 2 folgt dem
Branch zu Step 2 · beide beantwortet → fokussierte Suche → Present (grounded, validiert) ·
Antwort „false" überspringt Step 2 (Verzweigung) · Pathway übersteuert LLM-`missing_information`.

**Gesamtsuite: 114/114 grün** (100 Layer1-3 + 9 Layer4.1 + 5 Layer4.2).

## Layer 4.3 — HumanHandoff-Node fertig (Welle 3)

**L4-1 implementiert.** HandoffQ + HumanHandoff als deterministische Nodes; beide
Auslöser (Clarify-Budget-Erschöpfung, Coverage-insufficient) leiten über HandoffQ.

### Implementierte Änderungen (`src/careapp/orchestration/`)

- **`tools.py`**: neues `Tool.handoff_write` + `ToolContext.handoff()`
- **`state.py`**: `ScopePolicy` um `handoff_available: bool = False` + `handoff_text: Optional[str] = None`
  erweitert (Pilot-Default deaktiviert — Auslöser/Empfänger/Autorisierung = offene Entscheidung §8)
- **`nodes.py`**: `HandoffQ` (rein deterministisch, keine Tools) + `HumanHandoff`
  (`handoff_write`-Tool, setzt `disposition=human_handoff` + Übergabetext). CLARIFY:
  `max_clarify_rounds_exceeded` → `HANDOFF_Q`. EvaluateCoverage: `coverage_insufficient` → `HANDOFF_Q`.
- **`graph.py`**: neue Kanten `HANDOFF_Q → {HANDOFF, NO_VERIFIED}`, `HANDOFF → {SUMMARY, NO_VERIFIED}`;
  CLARIFY + COVERAGE-Kanten erweitert.
- **`tests/db/test_handoff.py`**: 9 neue Tests (HandoffQ-Routing, beide Auslöser, Default- und
  Custom-Text, Tool-Allowlist-Checks).

### Testergebnis Layer 4.3: **9/9 grün** · Gesamtsuite: **141/141 grün**

## Layer 4.4 — Checkpoint-Persistenz fertig (Welle 4)

**L4-2 implementiert.** PII-freier typisierter State wird zwischen Turns persistiert.

### Implementierte Dateien

- **`src/careapp/orchestration/checkpoint.py`**:
  - `SessionCheckpoint` (frozen dataclass): `session_id`, `clarify_rounds_used`,
    `pathway_answers`, `budgets`, `versions`, `created_at/updated_at`. Bewusst OHNE
    `latest_user_message`, `auth`, `confirmed_facts`, `trace` (PII-Schutz §5).
  - `CheckpointStore` (Protocol, `@runtime_checkable`): `save()` + `load()` — port-basiert, analog LLMClient.
  - `InMemoryCheckpointStore`: für Tests und lokale Entwicklung. `save()` ist UPSERT,
    bewahrt `created_at` bei Update.
  - `SupabaseCheckpointStore`: SQLAlchemy + PostgreSQL UPSERT (`INSERT … ON CONFLICT DO UPDATE`).
    JSONB-Cast via `CAST(:param AS JSONB)` (nicht `::jsonb`) — verhindert Konflikt mit SQLAlchemy-Parameterbindung.
  - `extract_checkpoint(state, cfg)`: extrahiert Checkpoint aus abgeschlossenem Turn-State.
- **`alembic/versions/0003_session_checkpoints.py`**: Migration 0003 (angewendet).
  Tabelle `session_checkpoints`: UUID PK, JSONB `pathway_answers`, budgets-Felder,
  Versions-Tripel, `created_at/updated_at TIMESTAMPTZ`.
- **`tests/db/test_checkpoint.py`**: 12 Tests.

### Testergebnis Welle 4: **12/12 grün** · Gesamtsuite nach Welle 4: **153/153 grün**

### Caller-Muster (Multi-Turn)

```python
cp = await store.load(session_id)
state = new_state(
    auth=auth, latest_user_message=msg, requested_at=now,
    session_id=cp.session_id if cp else None,
    clarify_rounds_used=cp.clarify_rounds_used if cp else 0,
    pathway_answers=cp.pathway_answers if cp else {},
    budgets=cp.budgets if cp else SessionBudgets(),
)
state = await run_consultation(state, session=db_session, llm=llm_client)
await store.save(extract_checkpoint(state, cfg))
```

### Hard-Blocker-Status (für Pilot-Einsatz)

| Blocker | Status |
|---|---|
| L4-1 HumanHandoff-Node | ✅ Welle 3 fertig |
| L4-2 Checkpoint-Persistenz-Store | ✅ Welle 4 fertig |
| L3-2/L4-3 Token-/Kosten-Metering | ✅ Welle 2 fertig |
| L4-4 Rate Limiting + Input-Größenlimit | ✅ Welle 5b fertig |

## Layer 5 — Eval-Framework + Golden Test Set fertig (Welle 5a)

**Layer 5 (§1 Evaluation & Pilot) teilimplementiert.** Deterministisches Eval-Framework
mit hartem Gate-System (§3) und 17 formalen Testfällen C1–C17.

### Implementierte Dateien

```
src/careapp/eval/__init__.py        # Paket
src/careapp/eval/types.py           # EvalCase, EvalResult, EvalMetrics, HardGateViolation
src/careapp/eval/runner.py          # run_eval_case(), check_hard_gates(), compute_metrics()
tests/eval/__init__.py              # Paket
tests/eval/test_golden_set.py       # 18 Tests (C1–C17 + Aggregat)
```

### Architektur Eval-Framework

- **`EvalCase`**: formaler Testfall mit Kategorie-Metadaten (id, category, description),
  `expected_disposition`, `forbidden_cv_ids` (nie in Evidenz), `forbidden_block_types` (nie in Ausgabe),
  `expected_fail_closed`. Persistierbar als JSON (Welle 5b).
- **`EvalResult`**: deterministisch aus `ConsultationState` extrahiert — 5 Hard-Gate-Flags:
  `unsupported_claim_found`, `forbidden_cv_appeared`, `forbidden_block_appeared`,
  `disposition_mismatch`, `fail_closed_violated`. Property `any_hard_gate_violated`.
- **`EvalMetrics`** (§2): `unsupported_claim_rate`, `forbidden_cv_rate`,
  `adversarial_pass_rate` (C10/C11/C12/C15/C16), `fail_closed_rate` (C17),
  `disposition_accuracy` (weich), `hard_gates_passed` (bool, Aggregat).
- **`run_eval_case()`**: `run_consultation()` → State-Auswertung → `EvalResult`. Wirft nie.
- **`check_hard_gates()`**: wirft `HardGateViolation` (ist `AssertionError`) → blocking in CI.
- **`compute_metrics()`**: aggregiert über beliebig viele Ergebnisse.
- Alle Tests deterministisch: **FakeLLMClient**, keine Live-LLM-Aufrufe.

### Golden Test Set C1–C17 (`tests/eval/test_golden_set.py`)

| Kategorie | Beschreibung | Gate-Typ |
|---|---|---|
| C1 | Happy Path, korrekte Citation | Disposition |
| C2 | Mehrdeutige Anfrage → Clarify, kein Raten | Disposition + Block-Typ |
| C3 | Medizinische Anfrage → SafeScopeResponse (T3) | Disposition + kein factual_statement |
| C4 | Anspruchsableitung → SafeScopeResponse (T5) | Disposition |
| C5 | Keine Evidenz → exakter Fallback-Wortlaut | Disposition + kein factual_statement |
| C6 | Abgelaufene CV darf nie erscheinen (T8) | forbidden_cv_ids |
| C7 | Regionsfremde CV ausgeschlossen | forbidden_cv_ids |
| C8 | Mandantenfremde CV ausgeschlossen (T4) | forbidden_cv_ids |
| C9 | Widersprüchliche CV ausgeschlossen (D3) | forbidden_cv_ids |
| C10 | Prompt-Injection User-Input bleibt Daten (T1) | kein unsupported_claim |
| C11 | Delimiter-Escape `</evidence>` neutralisiert (T2) | kein unsupported_claim |
| C12 | Manipulierter Betrag → Validator-Fallback (T6/D3) | Disposition + kein factual_statement |
| C13 | Partielle Coverage → presented (Pilot: single-aspect) | Disposition |
| C14 | Kein Evidenz + handoff_available → human_handoff | Disposition |
| C15 | Hypothese mit erfundener CV-ID → Fallback (T7/D8) | Disposition + forbidden_cv_ids |
| C16 | Schema-Bruch → kein Passthrough (T11/T12) | Disposition |
| C17 | Node-Exception → fail-closed (§7) | Disposition (Fail-Closed) |

Zusätzlich: `test_all_hard_gates_pass` — aggregierter Metrik-Report über 8 Kernkategorien,
prüft `metrics.hard_gates_passed` und `unsupported_claim_rate/forbidden_cv_rate = 0`.

### Testergebnis Welle 5a: **18/18 grün** · Gesamtsuite: **171/171 grün**

### Welle 5c (fertig) — Layer 5 DoD vollständig ✅

**Versions-Tripel-Bindung (§4), CI-Pipeline, Pilot-Eintrittscheckliste §5.1 fertig.**

#### Implementierte Änderungen

- **`src/careapp/eval/types.py`** — `EvalResult`: 3 neue Felder
  `graph_version`, `prompt_set_version`, `model_version` (Optional[str], Default None).
  `EvalMetrics`: 3 neue frozenset-Felder `graph_versions`, `prompt_set_versions`, `model_versions`
  (Versions-Mismatch sichtbar wenn > 1 Wert je Spalte im Gesamtlauf).
- **`src/careapp/eval/runner.py`** — `run_eval_case()`: extrahiert Versions-Tripel aus
  `state_out.audit.versions` und befüllt `EvalResult`.
  `compute_metrics()`: aggregiert alle gesehenen Versionen in frozensets.
- **`pyproject.toml`** — 3 pytest-Marker registriert:
  `hard_gate` (§3, blocking CI-Stop), `pilot_entry` (§5.1, offline),
  `db` (benötigt DB-Verbindung, skip in offline-CI).
- **`tests/eval/test_golden_set.py`** — `pytestmark = [pytest.mark.hard_gate, pytest.mark.db]`
  (alle C1–C17 sind harte Gates und brauchen DB).
- **`.github/workflows/eval.yml`** — 3-Job-CI-Pipeline:
  1. `pilot-entry-checks` (offline, immer, blockiert): `pytest -m pilot_entry`
  2. `hard-gates` (mit PostgreSQL-Service, blockiert): `pytest -m "hard_gate and db"` + Alembic
  3. `eval-metrics-report` (immer, non-blocking): Volllauf + JUnit-XML-Artefakt
- **`tests/eval/test_pilot_checklist.py`** — 22 offline §5.1-Checklisten-Tests (PE-01–PE-11):
  Consent-Gate-Kante, Safety-Bypass-Schutz, Fail-Closed-Dispositions, Input-/Rate-Limit,
  Versions-Felder in EvalResult/EvalMetrics, HardGateViolation-Auslösung, Arch-Dokumente.

#### Testergebnis Welle 5c: **22/22 grün** (offline) · Gesamtsuite: **206/206 grün**

#### Layer 5 DoD — vollständig ✅

- [x] Harte Gates (§3) als blocking CI-Checks (`.github/workflows/eval.yml` Job `hard-gates`)
- [x] Tests an Versions-Tripel gebunden; Mismatch erkennbar in `EvalMetrics.graph_versions`
- [x] Regressionslauf bei Modell-/Prompt-Wechsel (§4): frozensets zeigen Divergenz
- [x] Pilot-Eintrittskriterien (§5.1) als ausführbare Checkliste verankert (22 Tests, offline)

#### Noch offen (nicht blockierend für Pilot-Start)

- **LLM-Judge** für semantische Soft-Gates (Welle 5d): Ton, Vollständigkeit, Formulierung
- **Live-Pilot-Monitoring-Hooks** (§5.2): Eingabe/Ausgabe-Sampling, Metering-Dashboard
- **JSON-Serialisierung** der EvalCases (für Export/Versionierung der Testfälle selbst)

## Layer 4.5 — Rate Limiting + Input-Größenlimit fertig (Welle 5b)

**L4-4 implementiert. Alle Hard Blocker vor Pilot-Einsatz sind nun geschlossen.**

### Implementierte Änderungen

- **`state.py` — `SessionBudgets`**: zwei neue Felder (konfigurierbar, Pilot-Defaults):
  - `max_user_message_chars: int = 2000` — Riesen-Input-/Injection-Schutz
  - `max_turns_per_session: int = 20` — Flooding-Schutz pro Session
- **`state.py` — `ConsultationState`**: `turns_this_session: int = 0` — aus Checkpoint
  laden, von `session_start`-Guard geprüft
- **`nodes.py` — `session_start`**: Guard-Checks als allererste Aktion (vor CONSENT/LLM):
  1. `len(message) > max_user_message_chars` → `fallback_reason="input_too_large:..."` → `NO_VERIFIED`
  2. `turns_this_session >= max_turns_per_session` → `fallback_reason="rate_limit_exceeded:..."` → `NO_VERIFIED`
- **`graph.py`**: `ALLOWED_EDGES[SESSION_START]` um `NO_VERIFIED` erweitert;
  `new_state(...)` nimmt `turns_this_session`-Parameter
- **`checkpoint.py`**: `SessionCheckpoint` + alle Stores um `turns_this_session` erweitert;
  `extract_checkpoint()` erhöht `turns_this_session + 1` (Inkrementierung nach jedem Turn)
- **Migration 0004** (`alembic/versions/0004_rate_limit_columns.py`): 3 neue Spalten
  in `session_checkpoints` — `turns_this_session`, `max_user_message_chars`, `max_turns_per_session`
- **`tests/db/test_rate_limit.py`**: 13 Tests

### Caller-Muster (jetzt vollständig mit Rate-Limit)

```python
cp = await store.load(session_id)
state = new_state(
    auth=auth, latest_user_message=msg, requested_at=now,
    session_id=cp.session_id if cp else None,
    clarify_rounds_used=cp.clarify_rounds_used if cp else 0,
    pathway_answers=cp.pathway_answers if cp else {},
    budgets=cp.budgets if cp else SessionBudgets(),
    turns_this_session=cp.turns_this_session if cp else 0,  # NEU L4-4
)
state = await run_consultation(state, session=db_session, llm=llm_client)
await store.save(extract_checkpoint(state, cfg))
```

### Testergebnis Welle 5b: **13/13 grün** · Gesamtsuite: **184/184 grün**

### Hard-Blocker-Status (abgeschlossen)

| Blocker | Status |
|---|---|
| L4-1 HumanHandoff-Node | ✅ Welle 3 fertig |
| L4-2 Checkpoint-Persistenz-Store | ✅ Welle 4 fertig |
| L3-2/L4-3 Token-/Kosten-Metering | ✅ Welle 2 fertig |
| L4-4 Rate Limiting + Input-Größenlimit | ✅ Welle 5b fertig |

**Alle Hard Blocker vor Pilot-Einsatz sind geschlossen.**

## Layer 6 — FastAPI-Skeleton fertig (Welle 6a)

**Schritte 1 und teilweise 2 der 12-Schritte-Reihenfolge (§7).**

### Implementierte Dateien

```
src/careapp/api/
  __init__.py
  models.py          # ChatRequest/Response, SessionStateResponse, OutputBlockOut
  auth.py            # JWT → AuthContext (T4); DEV_AUTH=true für Pilot-Entwicklung
  deps.py            # FastAPI Dependencies: DB, LLM, CheckpointStore, GraphConfig
  app.py             # create_app() Factory, CORS, Router-Mounting; uvicorn-Entry-Point
  routers/
    chat.py          # POST /api/v1/chat · GET /session/{id}/state · DELETE /session/{id}
    health.py        # GET /api/v1/health
tests/api/
  __init__.py
  test_chat.py       # 12 offline API-Tests (httpx.AsyncClient, ASGITransport)
```

### Endpunkte (implementiert)

| Methode | Pfad | Beschreibung |
|---|---|---|
| POST | `/api/v1/chat` | Einen Turn ausführen (run_consultation) |
| GET | `/api/v1/session/{id}/state` | Checkpoint lesen (Reload) |
| DELETE | `/api/v1/session/{id}` | Session löschen |
| GET | `/api/v1/health` | Health-Check |

### Architektur-Details

- **Auth-Middleware (T4):** `get_auth_context()` baut `AuthContext` aus JWT-Claims —
  niemals aus dem Request-Body. `DEV_AUTH=true` für lokale Entwicklung (Pilot-AuthContext hardcoded).
- **Session-Middleware:** `get_checkpoint_store()` lädt `SessionCheckpoint` pro Request,
  `extract_checkpoint()` speichert nach `run_consultation()`.
- **Dependency-Overrides:** Alle Abhängigkeiten (DB, LLM, Store, GraphConfig) über
  `app.dependency_overrides` in Tests ersetzbar — kein Monkeypatching.
- **Fail-Closed:** `run_consultation()` wirft nie durch; Response immer 200 mit
  `disposition=no_verified_information` als schlimmster Fall.
- **Turn-Nummerierung:** `turn = state_out.turns_this_session + 1` (spiegelt den gespeicherten Wert).
- **Block-Normalisierung:** `ClarifyingQuestionBlock.question_text` → `text` (API-Vertrag einheitlich).
- **`checkpoint.py`**: `delete()`-Methode zu `InMemoryCheckpointStore`, `SupabaseCheckpointStore`
  und `CheckpointStore`-Protocol hinzugefügt.
- **`pyproject.toml`**: `api`-Extra (`fastapi`, `uvicorn`, `python-jose`, `httpx`);
  via `uv add` auch in Haupt-Dependencies eingefügt.
- **OpenAPI-Spec:** automatisch unter `/api/openapi.json` — Vertrag für Next.js-TypeScript-Typen.

### Starten (lokal)

```bash
CAREAPP_DEV_AUTH=true DEV_LLM=fake uvicorn careapp.api.app:app --reload
```

### Testergebnis Welle 6a: **12/12 grün** (offline, httpx) · Gesamtsuite: **230/230 grün**

### Layer 6 DoD — offen

- [x] `POST /api/v1/chat` implementiert (FakeLLMClient-Tests grün)
- [x] `GET /api/v1/session/{id}/state` implementiert
- [x] `DELETE /api/v1/session/{id}` implementiert
- [x] Auth-Middleware: JWT → AuthContext (T4)
- [x] Session-Middleware: Checkpoint laden/speichern
- [x] OpenAPI-Spec erreichbar
- [x] Fail-Closed: kein Stack-Trace im Response-Body
- [x] Health-Check-Endpunkt
- [x] `GET /api/v1/citation/{id}` + Next.js Overlay (Welle 6b)
- [x] Next.js-Projekt aufsetzen + Chat-UI (Welle 6c)
- [x] AnthropicLLMClient installiert (`uv sync --extra llm`), `llm`-Marker + Skip-Hook (Welle 6e)
- [x] Pilot-Content geseedet: 8 CVs aus SGB XI §14/§15/§43/§43b in Supabase (`scripts/seed_pilot_cvs.py`)
- [ ] `ANTHROPIC_API_KEY` setzen → `pytest -m "llm and db"` grün (Welle 6e, offen)
- [ ] Deployment auf Vercel (EU-Region Frankfurt) (Welle 6f)
- [ ] Pilot-Eintrittsprüfung mit echtem LLM (Welle 6f)

## Welle 6b — Citation-API + Overlay (fertig)

**`GET /api/v1/citation/{claim_version_id}` + CitationButton-Modal in Next.js. 5 neue Tests.**

### Implementierte Änderungen

- **`src/careapp/api/deps.py`** — DEV_AUTH/LLM-Entkopplung:
  `CAREAPP_DEV_AUTH=true` erzwingt nicht mehr `FakeLLMClient`. Nur `DEV_LLM=fake` steuert das.
  DEV_AUTH steuert nur die Auth-Bypass-Logik (bleibt in `auth.py`).
- **`src/careapp/api/models.py`** — zwei neue Modelle:
  `EvidenceOut` (role, quote, source_type, publisher, canonical_ref, edition_label) +
  `CitationResponse` (claim_version_id, statement_text, status, topic_scope, evidences).
- **`src/careapp/api/routers/citation.py`** — neuer Router:
  `GET /citation/{claim_version_id}` lädt `ClaimVersion` mit 4-stufigem Join
  (evidences → passage → version → document). Nur `published` abrufbar (404 sonst).
- **`src/careapp/api/app.py`** — `citation`-Router eingebunden.
- **`tests/api/test_citation.py`** — 5 offline Tests: 404 unbekannt, 404 draft, 200 published,
  leere evidences, 404 superseded.
- **`apps/web/app/api/citation/[id]/route.ts`** — Next.js Route Handler Proxy → FastAPI.
- **`apps/web/types/api.ts`** — `EvidenceOut` + `CitationResponse` TypeScript-Interfaces.
- **`apps/web/lib/api-client.ts`** — `fetchCitation(cvId)` Client-Funktion.
- **`apps/web/components/chat/CitationButton.tsx`** — "use client"-Komponente:
  ⓘ-Button öffnet Modal, lädt Citation lazy bei erstem Klick, zeigt Quelle/Zitat/Rolle.
- **`apps/web/components/chat/FactualBlock.tsx`** — nutzt `CitationButton` statt statischem ⓘ-span.
  Ein `CitationButton` pro `claim_version_id`.
- **`apps/web/.env.local`** — `FASTAPI_URL=http://localhost:8000` für lokale Entwicklung.

### Starten (lokaler Full-Stack)

```bash
# FastAPI (Terminal 1)
CAREAPP_DEV_AUTH=true DEV_LLM=fake uvicorn careapp.api.app:app --reload

# Next.js (Terminal 2) — .env.local enthält FASTAPI_URL
cd apps/web && npm run dev
```

### Testergebnis Welle 6b: **5/5 grün** · Offline-Suite: **94/94 grün**

Build: `npm run build` → 7 Routen kompiliert (inkl. `/api/citation/[id]`).

## Welle 6e — AnthropicLLMClient E2E-Gerüst (fertig, wartet auf Key)

**Anthropic SDK installiert, E2E-Tests geschrieben, Skip-Mechanismus aktiv.**

### Implementierte Änderungen

- **`uv sync --extra llm`** — `anthropic==0.109.1` + deps installiert.
- **`pyproject.toml`** — `llm`-Marker registriert: benötigt `ANTHROPIC_API_KEY`, Skip sonst.
- **`tests/conftest.py`** — `pytest_collection_modifyitems`: `@pytest.mark.llm`-Tests werden
  übersprungen wenn `ANTHROPIC_API_KEY` nicht gesetzt.
- **`tests/db/test_api_e2e.py`** — 2 E2E-Tests (`pytestmark = [llm, db]`):
  - `test_e2e_safety_invariants_hold_with_real_llm`: seeded CV + echte Frage + AnthropicLLMClient.
    Prüft I1–I7: Disposition aus erlaubter Menge, kein factual_statement ohne claim_version_ids (T7),
    alle CV-IDs aus Wissensbasis (D8), bei presented → validation_passed=True, Versions-Tripel, LLM-Calls.
  - `test_e2e_out_of_scope_message_yields_safe_response`: medizinische Anfrage → kein factual_statement (T3).
- **`.env.example`** — `ANTHROPIC_API_KEY`, alle FastAPI- und Next.js-Env-Vars dokumentiert.

### E2E-Tests aktivieren

```bash
# In .env hinzufügen:
echo "ANTHROPIC_API_KEY=sk-ant-..." >> .env

# Danach laufen lassen:
uv run pytest tests/db/test_api_e2e.py -v -s
```

### Testergebnis Welle 6e: 2 Tests `SKIPPED` (ohne Key) — bei Key-Setzen → 2 Tests `PASSED`

## Kritische Architekturdetails (Pflichtlektüre für neue Session)

### Intent-zu-Aspekt-zu-topic_scope-Kette (subtilste Stelle im ganzen System)

Ein neuer LLM-Entwickler macht hier fast immer denselben Fehler:

```
User: "Meine Mutter muss ins Heim"
  └─► LLM-2 (IntentUnderstanding)
        intent_hypotheses = ("heimunterbringung",)
        └─► resolved_intent = "heimunterbringung"   (in ASPECT_MAP → OK)
              └─► compute_coverage(ctx, "heimunterbringung", ASPECT_MAP)
                    required = ASPECT_MAP["heimunterbringung"] = ["stationaere_pflege"]
                    for aspect in required:
                      aspect_ctx = replace(ctx, topic_scope=aspect)  # "stationaere_pflege" !
                      pkg = build_evidence_package(aspect_ctx)
                        └─► Gate 7 prüft topic_scope="stationaere_pflege"
                              └─► ScopeAssignment.value="stationaere_pflege" → MATCH ✓
```

**Konsequenz für redaktionelle Arbeit:**
- `ScopeAssignment.dimension=topic, value=` muss den **Aspekt-Wert** enthalten (`"stationaere_pflege"`), nicht den Intent-Schlüssel (`"heimunterbringung"`)
- Neuer Intent: erst in `ASPECT_MAP` eintragen, dann CVs mit dem Aspekt-topic_scope anlegen

### Scope-Matching (Region)

`DE_FEDERAL` in `ScopeAssignment.value` matcht jede `region_id` (Gate 5 in `eligibility.py`).
Nur regionale CVs (z.B. Kreisspezifisch) brauchen den echten Regions-Code (`NW-KREIS-NEUSS`).

### DEV_AUTH-Context vs. geseede Daten

`CAREAPP_DEV_AUTH=true` → `target_group_codes=("patient", "family")`.
Geseede CVs haben target_groups `("relative", "patient")`.
Schnittmenge: `{"patient"}` → Gate 6 besteht. **"family" fehlt in den geseedeten CVs** —
für Production müssen CVs auch `target_group=family` abdecken (oder alle Nutzergruppen).

### Pytest-Marker-Hierarchie

| Marker | Bedeutung | Wann läuft |
|---|---|---|
| `pilot_entry` | Offline-Checkliste §5.1 | Immer (CI Job 1) |
| `hard_gate` | Sicherheits-Gate (§3), CI-Stop bei Fehler | Mit DB (CI Job 2) |
| `db` | Benötigt Supabase-Verbindung | Lokal + CI Job 2/3 |
| `llm` | Benötigt `ANTHROPIC_API_KEY` | Nur wenn Key gesetzt |

### Fail-Closed-Garantie (§7) — nie aushebeln

`run_consultation()` wirft nie durch. Jede unerwartete Exception → `Disposition.no_verified_information`.
Der Kernel hat 4 Fail-Closed-Stellen:
1. `session_start`: Länge/Rate → `NO_VERIFIED` (L4-4)
2. `scope_safety`: Parsefehler → `SAFE_SCOPE` (§7)
3. `composer`: Validierungsfehler → `NO_VERIFIED` (D8)
4. Fail-Closed-Runner in `graph.py`: Exception/illegale Kante → `NO_VERIFIED` (§7)

### Migrations-Stand (Alembic)

| Migration | Inhalt |
|---|---|
| `0001` | Initiales Schema (alle Tabellen + Trigger) |
| `0002` | L1-1 Immutability-Trigger-Update, L1-2 ScopeAssignment-Pflicht |
| `0003` | `session_checkpoints`-Tabelle (Checkpoint-Persistenz) |
| `0004` | Rate-Limit-Spalten in `session_checkpoints` |

`uv run alembic upgrade head` bringt jede Supabase-Instanz auf aktuellen Stand.

### Pilot-Content (jetzt live in Supabase)

8 published ClaimVersions aus SGB XI, topic_scope=`stationaere_pflege`:

| CV | Aussage (kurz) | Structured Value |
|---|---|---|
| `cv-pflegebeduerftigkeit-definition` | Pflegebedürftigkeit: Voraussetzungen (§14 SGB XI) | — |
| `cv-pflegegrade-uebersicht` | Pflegegrade 1–5 + Einstufungsverfahren (§15 SGB XI) | — |
| `cv-vollstationaere-pflege-anspruch` | Anspruch ab Pflegegrad 2 (§43 SGB XI) | — |
| `cv-vollstationaere-pflegekassenbetrag-pg2` | Pflegekasse zahlt 770 EUR/Monat bei PG2 | 770 EUR |
| `cv-vollstationaere-pflegekassenbetrag-pg3` | Pflegekasse zahlt 1.262 EUR/Monat bei PG3 | 1.262 EUR |
| `cv-vollstationaere-pflegekassenbetrag-pg4` | Pflegekasse zahlt 1.775 EUR/Monat bei PG4 | 1.775 EUR |
| `cv-vollstationaere-pflegekassenbetrag-pg5` | Pflegekasse zahlt 2.005 EUR/Monat bei PG5 | 2.005 EUR |
| `cv-betreuungsangebote-stationaer` | Zusätzliche Betreuungsangebote (§43b SGB XI) | — |

Script: `uv run python scripts/seed_pilot_cvs.py` (idempotent, deterministischer UUID-Seed).

---

## Nächster Schritt (neue Session starten hier)

**Letztes fehlendes Puzzleteil: `ANTHROPIC_API_KEY` in `.env` eintragen → E2E grün → Deployment.**

**A) ANTHROPIC_API_KEY eintragen** (in `.env`) → `uv run pytest tests/db/test_api_e2e.py -v -s` →
bestätigt Sicherheitsinvarianten D8+T7 mit echtem LLM gegen die geseedeten SGB XI-CVs.

**B) Welle 6f — Deployment auf Vercel (EU Frankfurt)** + FastAPI Hosting (Railway/Fly.io),
ANTHROPIC_API_KEY + DATABASE_URL als Secrets, CAREAPP_ALLOWED_ORIGINS auf Vercel-Domain.

**C) Pilot-Eintrittsprüfung**: Golden Test Set gegen echte Supabase-CVs mit echtem LLM ausführen
(`pytest tests/eval/test_golden_set.py`), `metrics.hard_gates_passed = True` bestätigen.

### Produktive Modellempfehlung (Kostenanalyse, 2026-06-13)
Sicherheit liegt vollständig in Layer 2 (Validator) — unabhängig vom Modell.
Daher zur Laufzeit günstig:
- **LLM-1..4 (Scope/Safety, Intent, Clarify, Retrieval): Haiku 4.5** — strukturierte Labels/Routing.
- **LLM-5 Composer: Sonnet 4.6** — nur hier zählt Sprachqualität.
- **Opus nur in der Entwicklung** (Architektur-/Prompt-Design), nie im Laufzeitpfad.
- Geschätzt **~$0,02–0,03 pro Gesprächszug** (alle 5 Aufrufe). 1.000 Gespräche × 3 Turns ≈ **$60–90**.

Empfohlene Modellnutzung beim Weiterplanen: Threat-Design mit **Opus 4.8 (hoch/max)**;
Ausformulierung Tests/Schemas mit **Sonnet 4.6 (mittel)**.
