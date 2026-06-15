# CareApp — Codex Agent Instructions

Safety-critical advisory chatbot for the German care system (Pflegeberatung).
Every factual claim must be backed by a reviewed, published ClaimVersion from the database.
No unverified claims may ever reach the user interface.

---

## Architecture (6 Layers)

| Layer | What it does | Location |
|---|---|---|
| 1 Data Model | Versioned knowledge base | `src/careapp/db/models/` |
| 2 Control Core | Deterministic gates D1–D8 | `src/careapp/domain/` |
| 3 LLM Contracts | Strict Pydantic schemas, Threat T1–T13 | `src/careapp/llm/` |
| 4 Orchestration | Static graph, Fail-Closed runner | `src/careapp/orchestration/` |
| 5 Evaluation | Golden test set C1–C17, Hard Gates | `src/careapp/eval/`, `tests/eval/` |
| 6 API & UI | FastAPI + Next.js 16 | `src/careapp/api/`, `apps/web/` |

Full architecture: `docs/chatbot/`  
Current implementation status: `docs/chatbot/HANDOVER.md`

---

## Dev Setup

```bash
# Python backend
cp .env.example .env
# Fill in DATABASE_URL and optionally ANTHROPIC_API_KEY
uv sync --extra llm

# Run FastAPI (offline mode — no API key needed)
CAREAPP_DEV_AUTH=true DEV_LLM=fake uv run uvicorn careapp.api.app:app --reload

# Next.js frontend (separate terminal)
cd apps/web
cp .env.local.example .env.local   # or set FASTAPI_URL=http://localhost:8000
npm install
npm run dev
```

---

## Running Tests

```bash
# All offline tests (no DB, no LLM — fast, always run these first)
uv run pytest tests/ -q --ignore=tests/eval/test_golden_set.py --ignore=tests/db/

# DB integration tests (requires DATABASE_URL in .env)
uv run pytest tests/db/ -v

# Hard Gate evaluation (requires DB)
uv run pytest tests/eval/ -m "hard_gate and db" -v

# E2E with real LLM (requires ANTHROPIC_API_KEY)
uv run pytest tests/db/test_api_e2e.py -v -s

# Next.js build check
cd apps/web && npm run build
```

All offline tests must stay green. Never break existing tests.

---

## Critical Safety Rules — Read Before Touching Anything

### 1. Fail-Closed invariant (§7)
Every exception anywhere in the request path → safe fallback response.  
Never let an exception propagate to the user as an error message or empty response.  
Location: `src/careapp/orchestration/graph.py` → `run_consultation()`

### 2. Validator D8 (post-generation check)
After every LLM-5 call, `validate_statements()` checks every factual block:
- All `claim_version_ids` must exist in DB with `status=published`
- Topic must match the requested `topic_scope`
If validation fails → discard entire response → fallback.  
Location: `src/careapp/domain/validator.py`

### 3. AuthContext always from JWT (T4)
`AuthContext` (user_id, target_groups, region_id) is built exclusively from the validated JWT.  
Never accept it from request body or query params.  
Location: `src/careapp/api/auth.py`

### 4. Eligibility filter is Fail-Closed (D4)
Unknown value → `False`. Never `True` on uncertainty.  
Location: `src/careapp/domain/eligibility.py`

### 5. LLM schemas use `extra=forbid`
All Pydantic models for LLM output use `model_config = ConfigDict(extra="forbid")`.  
Unexpected fields → ValidationError → Fallback. Never loosen this.

### 6. Intent → topic_scope chain (critical)
LLM-2 returns intent → `ASPECT_MAP` (deterministic dict, no LLM) maps to `topic_scope`.  
`compute_coverage()` uses the **aspect value** ("stationaere_pflege"), NOT the intent key ("heimunterbringung").  
`ScopeAssignment.value` must contain the aspect value, not the intent.  
Location: `src/careapp/domain/coverage.py`

### 7. ClaimRelation is append-only
Never update or delete rows in `claim_relation`. Add new rows only.  
Status transitions follow `VALID_TRANSITIONS` in `src/careapp/api/routers/admin.py`.

---

## Database

- Supabase PostgreSQL, eu-central-1 (Frankfurt)
- Migrations: `uv run alembic upgrade head`
- Current head: migration `0004`
- Pilot content: `uv run python scripts/seed_pilot_cvs.py` (idempotent)
- Never write raw SQL that bypasses migrations

### Status workflow for ClaimVersions
```
draft → in_review → approved → published → superseded
                 ↘ withdrawn   ↘ withdrawn   ↘ expired
```

---

## Adding a New Topic (Lebenslage)

1. Add entry to `ASPECT_MAP` in `src/careapp/domain/coverage.py`
2. Create `ClaimVersion` rows in Supabase with matching `topic` ScopeAssignment
3. Add test cases to `tests/eval/test_golden_set.py`

---

## Key Files

| File | Purpose |
|---|---|
| `src/careapp/domain/coverage.py` | ASPECT_MAP + compute_coverage() |
| `src/careapp/domain/eligibility.py` | Gates D1–D8 |
| `src/careapp/domain/validator.py` | Post-generation validator D8 |
| `src/careapp/orchestration/graph.py` | Fail-Closed runner + graph edges |
| `src/careapp/orchestration/nodes.py` | 14 graph nodes |
| `src/careapp/llm/schemas.py` | LLM output schemas (strict Pydantic) |
| `src/careapp/api/routers/admin.py` | Admin endpoints + VALID_TRANSITIONS |
| `src/careapp/api/auth.py` | JWT → AuthContext (T4) |
| `scripts/seed_pilot_cvs.py` | Pilot content seeding (idempotent) |
| `docs/chatbot/HANDOVER.md` | Full implementation status |

---

## What NOT to Do

- Do not add `if os.environ.get("SKIP_VALIDATION")` bypasses anywhere
- Do not set `extra="allow"` or `extra="ignore"` on LLM schemas
- Do not return factual content without `claim_version_ids`
- Do not allow `status != published` CVs to reach the chat response
- Do not commit `.env`, `.env.local`, or `apps/web/.env.local`
- Do not use `git commit --no-verify`
- Do not remove the Fail-Closed try/except in `graph.py`
- Do not hardcode credentials or tokens in source files

---

## Environment Variables

See `.env.example` for all required variables.  
Never commit the actual `.env` file.  
Admin token: same value in `CAREAPP_ADMIN_TOKEN` for both FastAPI and `apps/web/.env.local`.

---

## Next Pending Tasks

1. Set `ANTHROPIC_API_KEY` → run `pytest tests/db/test_api_e2e.py` → first real E2E
2. Welle 6f: Deployment to Vercel (Next.js) + Railway/Fly.io (FastAPI)
3. Migration 0005: Add `authority_rank`, `source_url`, `valid_until` to `source_document`
4. Knowledge Graph: `GET /api/v1/admin/graph` endpoint + `/admin/graph` D3 page
5. Ingestion pipeline: PDF import + AI extraction + Vier-Augen approval
6. Add "family" target_group to seeded CVs for production correctness
