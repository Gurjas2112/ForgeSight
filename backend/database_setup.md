# Database Setup — ForgeSight

ForgeSight stores all operational state in **PostgreSQL** (Supabase-hosted in production) with the
**pgvector** extension for RAG embeddings. There is **no ORM** — the backend uses a raw `psycopg`
connection pool and parameterized SQL. The schema is idempotent and applied by a single runner.

- **Schema:** [`backend/db/migrations.sql`](db/migrations.sql)
- **Seeds:** [`backend/db/seed_accounts.sql`](db/seed_accounts.sql) (demo users) · `seed_data.sql` (equipment, sensors, breakdowns)
- **Runner:** [`backend/db/apply_migrations.py`](db/apply_migrations.py)
- **Connection:** [`backend/db/connection.py`](db/connection.py) — pooled, `DATABASE_URL`

---

## 1. Extensions & enums

- `vector` (pgvector) — 768-dim embeddings, HNSW index for cosine similarity.
- `pgcrypto` — `gen_random_uuid()` + bcrypt password hashing for seeds.
- Enums: `role_t(engineer,admin)`, `doc_type_t(manual,sop,report)`, `severity_t(info,warning,high,critical)`,
  `query_class_t(knowledge,live_status,action)`, `msg_role_t(user,assistant,agent_event)`,
  `verdict_t(up,down,fixed)`, `author_t(system,human)`, `pending_t(pending,approved,rejected)`,
  `wo_status_t(draft,open,in_progress,completed,cancelled)`.

---

## 2. Tables

**Identity**

| Table | Key columns | Purpose |
|---|---|---|
| `auth.users` | (Supabase-managed) | GoTrue accounts (email, encrypted password, app_metadata.role). |
| `profiles` | `id`→auth.users, `full_name`, `role`, `area` | App-side mirror of role; source for `/admin/users`. |

**Assets & condition monitoring**

| Table | Purpose |
|---|---|
| `equipment` | Asset master (id, name, zone, criticality, thresholds). |
| `sensor_readings` | Time-series: vibration_de/nde, bearing_temp, motor_current, rpm, load_pct. |
| `equipment_health` | Anomaly score, is_anomalous, rul_days, rul_band, contributing_sensors. |
| `alerts` | Severity-ranked anomalies (acked_at NULL = open). |
| `breakdown_history` | Past failures (fault_code, root_cause, downtime_hrs, verified). |
| `spares` | Inventory (part_no, stock_qty, lead_time_days, unit_cost_inr, supplier). |

**Knowledge (RAG)**

| Table | Purpose |
|---|---|
| `doc_chunks` | Corpus: content, section_ref, `embedding vector(768)`, doc_type (manual/sop/report). HNSW index. |
| `semantic_cache` | Query→response cache keyed by embedding (expires_at). |

**Conversations**

| Table | Purpose |
|---|---|
| `chat_sessions` | One row per conversation; `id` = LangGraph thread_id, `user_id`→auth.users, `title`, `equipment_id`, `updated_at`. |
| `chat_messages` | Ordered turns: `role` (user/assistant/agent_event), `content`, `card_json`, `agent_name`, `created_at`. |

**Governance, feedback, work**

| Table | Purpose |
|---|---|
| `feedback` | `verdict` (up/down/fixed), equipment_id, note — FR-6 improvement loop. |
| `logbook` | Shift handover & fix-confirmed entries. |
| `pending_actions` | HITL COMMIT proposals (status, decided_by, decided_at). |
| `audit_log` | Every authority allow/deny (+ signup downgrades) with `ts`. |
| `llm_usage` | Per-LLM-call token meter (backend, model, call_type, prompt/completion/total tokens, `cached`) — powers the admin token-usage monitor. |
| `llm_cache` | Persistent LLM response cache (key = sha256(backend\|model\|system\|user); `response` jsonb, `hits`) — a hit returns the card for 0 tokens. |
| `work_orders` | Maintenance tasks (status, priority, assignee, steps). |
| `reports` · `rejected_readings` | Generated PDFs · sensor-QA quarantine. |

**Analytic views** (read-only): `v_breakdown_stats`, `v_spares_status`, `v_alert_feed`,
`v_downtime_by_equipment` — backing `/plant/summary`, `/admin/metrics`, the Analyst agent's governed SQL.

---

## 3. Row-Level Security (defense in depth)

RLS is enabled on `chat_sessions`/`chat_messages` (`sessions_owner`: a user sees their own sessions,
admins see all). **Important:** the API connects with the **service-role** key (bypasses RLS), so the
application *also* filters by `user.id` explicitly in SQL (`/chat/sessions`,
`/chat/sessions/{id}/messages`). RLS is the backstop for any future anon-key access path.

---

## 4. Apply the schema

```bash
# 1 · point at the database
export DATABASE_URL='postgresql://...supabase pooler...'

# 2 · schema + RLS + seeds + corpus + work_orders + spares (idempotent)
uv run python backend/db/apply_migrations.py

# 3 · populate equipment_health + the seeded CRITICAL alert
uv run python backend/scheduler/health_scan.py --once
```

`apply_migrations.py` runs `migrations.sql` then the seed SQL, and falls back to the Supabase Admin API
for the GoTrue users it cannot insert directly. Re-running is safe (every statement is `IF NOT EXISTS` /
`ON CONFLICT`).

**Seeded demo accounts** (bcrypt-hashed): `engineer@demo.forgesight` / `admin@demo.forgesight`,
password `forgesight-demo`.

---

## 5. Corpus ingestion (RAG)

Embeddings are produced by `nomic-embed-text` and inserted into `doc_chunks`. See
[`../data/data_collection_flow.md`](../data/data_collection_flow.md) for how manuals, SOPs and
breakdown records become chunks, and `data/corpus/seed_corpus.py` → `corpus_ingest.sql`.

---

## 6. Production (Supabase)

1. Create a Supabase project; enable `vector` (`CREATE EXTENSION IF NOT EXISTS vector`).
2. Set backend secrets: `DATABASE_URL` (pooler URI), `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
   `SUPABASE_JWT_SECRET`.
3. Run `apply_migrations.py` once against the project.
4. The frontend uses `NEXT_PUBLIC_SUPABASE_URL` + `NEXT_PUBLIC_SUPABASE_ANON_KEY` for auth only.

See [`Backend_workflow.md`](Backend_workflow.md) for how the data layer is consumed at runtime.
