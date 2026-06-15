# CareApp Chatbot

Sicherheitskritische Beratungsplattform für das deutsche Gesundheits- und Sozialsystem.
Kernprinzip: Das LLM führt das Gespräch; jede Fachaussage stammt aus einer versionierten,
redaktionell freigegebenen Wissensbasis und wird vor Ausgabe deterministisch auf Belegbarkeit
geprüft. Unbelegte Aussagen erreichen die UI nie.

Pilot: **Lebenslage „Meine Mutter muss ins Heim"** — Kreis Neuss / Düsseldorf (NRW).

---

## Architektur (6 Schichten)

| Layer | Beschreibung | Status |
|---|---|---|
| 1 Datenmodell | Versionierte Wissensbasis (Claim/ClaimVersion/Evidence) | ✅ fertig |
| 2 Kontrollkern | Eligibility-Filter, Evidence Builder, Validator (D8) | ✅ fertig |
| 3 LLM-Verträge | Strikte Schemas LLM-1..5, Threat-Model T1–T13 | ✅ fertig |
| 4 Orchestrierung | Statischer Graph, Fail-Closed, Checkpoints, Rate-Limit | ✅ fertig |
| 5 Evaluation | Golden Test Set C1–C17, Hard Gates, CI-Pipeline | ✅ fertig |
| 6 API & UI | FastAPI + Next.js Chat, Citation-Overlay, Consent-Gate | 🟡 offen: E2E + Deployment |

Vollständige Architekturentscheidungen: [`docs/chatbot/`](docs/chatbot/)
Implementierungsstand (täglich aktuell): [`docs/chatbot/HANDOVER.md`](docs/chatbot/HANDOVER.md)

---

## Lokaler Start (vollständiger Stack)

### Voraussetzungen

- Python 3.12 via `uv` (`brew install uv`)
- Node.js 26 (`brew install node`)
- Supabase-Projekt (`DATABASE_URL` in `.env`)
- Optional: `ANTHROPIC_API_KEY` für echten LLM-Pfad

```bash
cp .env.example .env
# DATABASE_URL und ggf. ANTHROPIC_API_KEY eintragen
uv sync --extra llm   # Anthropic SDK mitinstallieren
```

### Terminal 1 — FastAPI

```bash
# Offline-Modus (FakeLLMClient, kein API-Key nötig)
CAREAPP_DEV_AUTH=true DEV_LLM=fake uv run uvicorn careapp.api.app:app --reload

# Produktionsmodus (echter LLM, API-Key in .env)
CAREAPP_DEV_AUTH=true uv run uvicorn careapp.api.app:app --reload
```

API-Docs: http://localhost:8000/api/docs

### Terminal 2 — Next.js

```bash
cd apps/web
# .env.local enthält FASTAPI_URL=http://localhost:8000
npm install
npm run dev
```

Chat: http://localhost:3000 → Consent-Gate → `/chat`

---

## Datenbank-Setup

Supabase-Projekt: `tbfzghhxeutbkbqubowp` (eu-central-1, Frankfurt).

```bash
# Migrationen anwenden
uv run alembic upgrade head

# Pilot-Inhalte seeden (SGB XI §14/§15/§43/§43b — idempotent)
uv run python scripts/seed_pilot_cvs.py

# Bestehende Daten prüfen (dry-run)
uv run python scripts/seed_pilot_cvs.py --dry-run
```

---

## Tests

```bash
# Alle Offline-Tests (kein DB, kein LLM)
uv run pytest tests/ -q --ignore=tests/eval/test_golden_set.py --ignore=tests/db/

# Alle DB-Tests gegen Supabase
uv run pytest tests/db/ -v

# Pilot-Eintrittsprüfung (Hard Gates — benötigt DB)
uv run pytest tests/eval/ -m "hard_gate and db" -v

# E2E mit echtem LLM (benötigt ANTHROPIC_API_KEY)
uv run pytest tests/db/test_api_e2e.py -v -s

# Next.js Build-Check
cd apps/web && npm run build
```

---

## Neue Inhalte hinzufügen

Ein neuer Themenbereich ("Lebenslage") braucht drei Einträge:

### 1. Redaktionelle CVs in Supabase anlegen

Vorbild: [`scripts/seed_pilot_cvs.py`](scripts/seed_pilot_cvs.py)

Pflicht-Felder pro ClaimVersion:
- `statement_text` — exakte, belegbare Fachaussage
- `status = published` — nur dann abrufbar
- `ScopeAssignment` (topic, region, target_group)
- `ClaimEvidence` mit wörtlichem `quote` aus Quelldokument

### 2. Intent → Aspekt in `coverage.py` eintragen

```python
# src/careapp/domain/coverage.py
ASPECT_MAP: dict[str, list[str]] = {
    "heimunterbringung": ["stationaere_pflege"],   # Pilot
    "neuer_intent":      ["neuer_topic_scope"],    # NEU
}
```

Der LLM (LLM-2) schlägt `intent_hypotheses` vor; `resolved_intent` wird
deterministisch gegen `ASPECT_MAP` gefiltert. Nur bekannte Intents kommen durch.

### 3. Scope-Matching verstehen

Der Eligibility-Filter prüft Gate 7 (`topic_scope`) mit dem **Aspekt-Wert**
(`"stationaere_pflege"`), nicht mit dem Intent-Schlüssel (`"heimunterbringung"`).
`compute_coverage()` ersetzt `ctx.topic_scope` für jeden Aspekt einzeln.

---

## Umgebungsvariablen (vollständig)

| Variable | Zweck | Pflicht |
|---|---|---|
| `DATABASE_URL` | Supabase PostgreSQL (asyncpg) | ✅ |
| `TEST_DATABASE_URL` | Testdatenbank (darf gleiche Supabase sein) | Nur Tests |
| `ANTHROPIC_API_KEY` | Echter LLM-Aufruf via Anthropic API | Für E2E + Prod |
| `CAREAPP_DEV_AUTH` | `true` → Pilot-AuthContext ohne JWT | Dev |
| `DEV_LLM` | `fake` → FakeLLMClient (kein API-Key nötig) | Dev |
| `DEV_INMEMORY_STORE` | `true` → InMemoryCheckpointStore | Dev |
| `CAREAPP_GRAPH_VERSION` | Audit-Label für den Graphen (Default: `graph-v1`) | Optional |
| `CAREAPP_PROMPT_VERSION` | Audit-Label für Prompt-Set (Default: `prompts-v1`) | Optional |
| `CAREAPP_MODEL_VERSION` | Audit-Label für Modell (Default: `models-v1`) | Optional |
| `CAREAPP_ALLOWED_ORIGINS` | CORS-Whitelist (Default: `http://localhost:3000`) | Prod |
| `FASTAPI_URL` | Next.js → FastAPI Proxy (in `apps/web/.env.local`) | Next.js |
| `SUPABASE_JWT_SECRET` | JWT-Validierung in Produktion | Prod |
| `CAREAPP_ADMIN_TOKEN` | Admin-Backend-Passwort (gleicher Wert in FastAPI + `apps/web/.env.local`) | Admin |

---

## Verzeichnisstruktur

```
src/careapp/
  db/models/       # SQLAlchemy-Modelle (claim.py, source.py, pathway.py)
  domain/          # Layer 2: evidence_builder, coverage, validator, eligibility
  llm/             # Layer 3: schemas, port, channels, scope_safety, composer, anthropic_adapter
  orchestration/   # Layer 4: graph, nodes, state, checkpoint, tools
  eval/            # Layer 5: types, runner
  api/             # Layer 6: app, auth, deps, models, routers/

apps/web/          # Next.js 16 (App Router, TypeScript, Tailwind)
  app/             # Pages + Route Handlers
  components/      # chat/, consent/
  lib/             # api-client.ts
  types/           # api.ts

tests/
  db/              # DB-Integrationstests (gegen Supabase)
  llm/             # Offline-Tests Layer 3
  eval/            # Eval-Framework-Tests + Pilot-Checkliste
  api/             # FastAPI-Tests (httpx, offline)

scripts/
  seed_pilot_cvs.py  # Pilot-Content-Seeding (SGB XI, idempotent)

docs/chatbot/      # Architekturentscheidungen + HANDOVER.md
alembic/           # Datenbankmigrationen (0001–0004)
```

---

## Sicherheitsinvarianten (Kerndokumentation)

| ID | Invariante | Durchsetzung |
|---|---|---|
| D8 | Jede `factual_statement` muss durch valide CV belegt sein | Post-Generation-Validator (Layer 2) |
| T7 | Kein `factual_statement` ohne `claim_version_ids` | LLM-Schema (Layer 3, extra=forbid) |
| T4 | AuthContext immer aus JWT, nie aus Request-Body | `auth.py` Dependency |
| D4 | Unbekannte Werte → false (Fail-Closed) | Eligibility-Filter (Layer 2) |
| §7 | Jede Exception → sichere Fallback-Antwort | Fail-Closed-Runner (Layer 4) |

Vollständige Liste: [`docs/chatbot/architecture-knowledge-and-control-core.md`](docs/chatbot/architecture-knowledge-and-control-core.md) (D1–D8) und [`docs/chatbot/architecture-llm-layers-and-threat-model.md`](docs/chatbot/architecture-llm-layers-and-threat-model.md) (T1–T13).

---

## Admin-Backend (redaktionelles Pflege-Interface)

Nicht-technische Redakteure verwalten Inhalte über `/admin`:

```bash
# CAREAPP_ADMIN_TOKEN in .env setzen, dann:
CAREAPP_DEV_AUTH=true DEV_LLM=fake CAREAPP_ADMIN_TOKEN=mein-passwort \
  uv run uvicorn careapp.api.app:app --reload

# In apps/web/.env.local: CAREAPP_ADMIN_TOKEN=mein-passwort (selber Wert)
cd apps/web && npm run dev
# → http://localhost:3000/admin → Login → Dashboard
```

| Route | Beschreibung |
|---|---|
| `/admin` | Dashboard (Statistiken, Schnellzugriff) |
| `/admin/claims` | Alle Fachaussagen (Filter nach Status) |
| `/admin/claims/new` | Neue Fachaussage anlegen (draft) |
| `/admin/claims/{id}` | Detail + Vier-Augen-Freigabe-Workflow |
| `/admin/sources` | Quelldokumente anlegen und Passagen importieren |

**FastAPI-Endpunkte** (Bearer-Token, dasselbe Token wie das Passwort):
`GET/POST /api/v1/admin/claims`, `PATCH /api/v1/admin/claims/{id}`,
`POST /api/v1/admin/claims/{id}/transition`, `POST /api/v1/admin/claims/{id}/approve`,
`GET/POST /api/v1/admin/sources`, `GET /api/v1/admin/stats`

**Vier-Augen-Workflow:**
1. Redakteur legt CV als `draft` an
2. Klick „Zur Prüfung einreichen" → `in_review`
3. Erste Person: Freigabe (Redakteur) → `approved`
4. Zweite Person: Veröffentlichen (Chefredakteur, Vier-Augen) → `published`

---

## Nächste Schritte

1. **`ANTHROPIC_API_KEY` eintragen** → `uv run pytest tests/db/test_api_e2e.py -v -s` → E2E grün
2. **Deployment**: Vercel (Next.js, EU Frankfurt) + Railway/Fly.io (FastAPI) + Secrets
3. **Pilot-Eintrittsprüfung**: `pytest tests/eval/ -m "hard_gate and db"` mit echtem LLM
