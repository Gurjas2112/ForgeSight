# Backend Workflow — ForgeSight API

The backend is a **FastAPI** application that exposes the governed multi-agent maintenance engine over
HTTP. It is the single boundary the frontend talks to, and it owns authentication, the LangGraph agent
controller, all deterministic tools (RAG · ML · governed SQL), persistence, the health scheduler, and
PDF reporting.

- **Entry point:** [`backend/server.py`](server.py) — `uvicorn backend.server:app`
- **Runtime:** Python 3.12 · FastAPI · Uvicorn · raw `psycopg` connection pool (no ORM)
- **Deploy:** Docker ([`backend/Dockerfile`](Dockerfile)) on Railway ([`railway.json`](../railway.json)), health-checked at `/healthz`
- **Config:** [`backend/config.py`](config.py) (pydantic-settings, loaded from `.env`)

---

## 1. Request lifecycle (a `/chat` turn)

```
HTTP POST /chat
  │
  ├─ current_user()  ── verify Supabase JWT (ES256/RS256/HS256) → AuthUser{id, role}
  │                      (falls back to the demo engineer when no/!invalid token)
  ├─ _ensure_session() ─ INSERT chat_sessions row (FK fix) + log the user message
  │
  ▼  controller.invoke(inputs, {thread_id: session_id})
  LangGraph AgentController:
    ingest_and_authorize → cache_lookup → classify_intent
      → charter-scoped agent pipeline (deterministic tool sequence, NOT a ReAct loop)
      → synthesize (SLM, constrained JSON)
      → guardrail_validate
      → { respond | human_gate (HITL) | repair | degrade }
  │
  ├─ SupabasePersistence.write_turn() ─ persist assistant card + agent_event rows (timestamps)
  ▼
HTTP 200  { card, delegations, citations, intent, query_class, awaiting_approval, session_id }
```

The SLM is invoked **only** at `synthesize`/`repair`. It narrates and fills typed schemas; it never
selects tools or computes numbers — those are deterministic pipelines. This is what makes every answer
reproducible and auditable.

---

## 2. Governance core (`backend/agent/`)

| Module | Responsibility |
|---|---|
| [`build.py`](agent/build.py) | Wires the `AgentController` (authority + guardrails + pipelines + SLM + caches + persistence). |
| `governance.py` | `AgentAuthority` (per-agent charters, budgets, allow/deny — every decision audited) + injection markers. |
| `pipelines.py` | The deterministic tool sequences for each chartered agent. |
| [`synthesis.py`](agent/synthesis.py) | `OllamaSynthesizer` — classify, synthesize card, one-shot repair. Ollama (local) or hosted (Groq/OpenAI). |
| [`persistence.py`](agent/persistence.py) | `SupabasePersistence.write_turn()` (assistant + agent_event rows) / `commit_action()` (HITL). |
| `prompt_builder.py` | Context-block serializer — **byte-parity** with `finetune/dataset/prompt_builder.py`. |

**Five chartered agents** (each emits one typed card):

| Agent | Card | Tools (fixed order) |
|---|---|---|
| Diagnostic | ranked root-cause + checklist/SOP | `retrieve_rag` → `match_history` |
| Reliability | RUL, risk, wait-assessment | `check_equipment_health` → `estimate_rul` |
| Supervisor | priority score (factor breakdown) | `score_priority` (rule-based) |
| Planner | spares & procurement (HITL) | `check_spares` → `procurement_rule` |
| Analyst | governed text-to-SQL | `query_records` (SELECT-only, curated views) |

---

## 3. Authentication & authorization

- **Verification:** [`backend/auth/jwt.py`](auth/jwt.py) — `verify_token()` decodes the Supabase access
  token (asymmetric ES256/RS256 via JWKS, or legacy HS256), reading `app_metadata.role`.
- **Signup:** `POST /auth/signup` → [`backend/auth/supabase_admin.py`](auth/supabase_admin.py)
  `create_user()` provisions a pre-confirmed GoTrue user and mirrors the role into `profiles`.
- **Input validation (server-side, the source of truth):** `SignupIn` uses pydantic `EmailStr`
  (RFC email → 422 on malformed) and a `password` `field_validator` (≥8 chars, ≥1 letter + ≥1 number).
  Duplicate emails raise `DuplicateUserError` → clean **409**. The frontend mirrors these rules in
  [`frontend/lib/validate.ts`](../frontend/lib/validate.ts) for instant feedback.
- **Privilege:** public signup is **engineer-only**; a self-assigned `admin` request is silently
  downgraded to engineer and recorded in `audit_log` (`_audit_signup_downgrade`). `require_admin`
  gates admin-only routes.
- **Audit:** [`backend/auth/audit.py`](auth/audit.py) — every authority allow/deny is written to
  `audit_log` (best-effort; never breaks the request path).
- **Email confirmation** (production opt-in SMTP flow) is intentionally deferred; demo accounts are
  pre-confirmed.

> Note: the backend uses the **service-role** connection pool, so Postgres RLS is *not* enforced at the
> app layer — per-user filtering (e.g. "only your own chat sessions") is done **explicitly in SQL**.

---

## 4. API surface (routes)

**Auth & chat**

| Method · Path | Purpose |
|---|---|
| `GET /healthz` | Liveness + DB check + which SLM/LLM is serving synthesis. |
| `POST /auth/signup` | Validated signup (EmailStr + password rules, engineer-only, 409 on dup). |
| `GET /auth/me` | Current `{id, role}`. |
| `POST /chat` | Run a governed turn → typed card. Creates the session row + logs the user message. |
| `POST /chat/approve` | Resume a paused `human_gate` (COMMIT approval). |
| `GET /chat/sessions` | **List the caller's conversations** (admins see all) — for history restore. |
| `GET /chat/sessions/{id}/messages` | **Ordered messages with timestamps** (owner/admin only; 403/404 otherwise). |

**Admin (system metrics — `require_admin`)**

| Method · Path | Purpose |
|---|---|
| `GET /admin/metrics` | Live aggregates: accounts by role, knowledge corpus, conversations, feedback, work orders, governance audit (24h), open alerts, plant KPI. |
| `GET /admin/users` | Account roster from `profiles`. |
| `GET /admin/audit` | Recent governance audit trail (allow/deny). |
| `GET /admin/llm-usage` | LLM token-usage detail: daily token/cache series + per-call-type breakdown. |

**Operations & dashboard** (all `current_user`)

`GET /equipment` · `GET /equipment/{id}` · `GET /equipment/{id}/context` · `GET /alerts` ·
`GET /plant/summary` · `GET /models/scorecard` · `GET /search` · `GET|POST|PATCH /work-orders[...]` ·
`GET /work-orders/{id}/export` · `GET /incidents[...]` (+ `/replay`, `/lessons`) · `GET /spares` ·
`GET /inventory/optimizer` · `GET /reliability/plant` · `GET /reliability/{id}` · `GET /leadership/roi` ·
`GET /maintenance/logbook` · `POST /maintenance/handover` · `GET /evidence` ·
`GET /reports/alert` · `GET /reports/shift-summary` · `POST /feedback`.

---

## 5. Tools (`backend/tools/`)

- [`ml_tools.py`](tools/ml_tools.py) — loads the published ML artifacts once (`@lru_cache`) and exposes
  `check_equipment_health`, `estimate_rul`, `analyze_defect`, `predict_failure`, `predict_pdm_24h`,
  `model_scorecard` (live held-out inference behind `/models/scorecard` and `/admin/metrics`).
- `rag.py` — hybrid retrieval over `doc_chunks` (pgvector + full-text; full-text-primary when no
  embedding backend).
- `text_to_sql.py` — governed, SELECT-only NL→SQL over curated analytic views.
- `plant_summary.py` — deterministic plant KPI computation (reused by `/plant/summary` and `/admin/metrics`).
- `work_orders.py` · `incidents.py` · `search.py` · `feedback_store.py` · reporting helpers.

---

## 6. LLM / SLM synthesis backend

Selected by `SYNTHESIS_BACKEND` in `.env`:

- `ollama` (default, on-prem): local Qwen via Ollama at `OLLAMA_HOST`. Set
  `OLLAMA_MODEL=qwen-forgesight` to serve the **fine-tuned** model (verified deployable — see
  [`../finetune/finetuning_workflow.md`](../finetune/finetuning_workflow.md)); base `qwen2.5:3b-instruct`
  is the safe default.
- `hosted` (cloud / Railway, no GPU): OpenAI-compatible API; `LLM_PROVIDER=groq`
  (`llama-3.3-70b-versatile`) by default. The public demo runs this path.

`/healthz` reports the active backend + model so the serving path is always observable.

**Token metering + response cache** ([synthesis.py](agent/synthesis.py)): every classify/synthesize/
repair call is dispatched through `_chat_json`, which first checks a persistent **`llm_cache`**
(keyed by `sha256(backend|model|system|user)`). A hit returns the stored card for **0 tokens**; a miss
calls the model, records prompt/completion/total tokens in **`llm_usage`**, and stores the response.
Both are best-effort (pool-gated) — a DB hiccup just means uncached/unmetered, never a failed turn.
The admin endpoints aggregate these into the token-usage monitor. Because the cache key includes the
full prompt (which embeds live numbers), changed data correctly misses the cache (no stale answers).

---

## 7. Persistence & scheduler

- **Chat memory is dual:** LangGraph checkpoints (agent state, keyed by `thread_id = session_id`) +
  `chat_messages` (UI-visible history). `/chat` now creates the `chat_sessions` row before invoking the
  controller, which fixes the FK that previously made history writes fail silently. The history is read
  back per-user via `/chat/sessions` and `/chat/sessions/{id}/messages` and restored by the global
  copilot widget.
- **Scheduler** ([`backend/scheduler/health_scan.py`](scheduler/health_scan.py)) — when
  `ENABLE_SCHEDULER=true`, re-scans equipment health every `SCHEDULER_INTERVAL_SECONDS` and raises
  severity-ranked alerts (FR-7 real-time alerting).

---

## 8. Run & test locally

```bash
uv run uvicorn backend.server:app --port 8000     # DATABASE_URL + Ollama (or hosted) configured
uv run pytest backend/tests -q                    # deterministic tools, guardrails, feedback, auth gating
curl localhost:8000/healthz
```

See [`database_setup.md`](database_setup.md) for schema/migrations and
[`../README.md`](../README.md) for the full stack and deployment.
