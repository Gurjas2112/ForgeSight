-- ForgeSight — full database schema (Supabase / Postgres + pgvector).
-- Mirrors forgesight-v3-final.md §1.5. Idempotent: safe to re-run.
-- Apply with: python backend/db/apply_migrations.py  (or psql $DATABASE_URL -f this file)

-- ============================================================================
-- 0. Extensions
-- ============================================================================
CREATE EXTENSION IF NOT EXISTS vector;        -- pgvector (768-dim embeddings)
CREATE EXTENSION IF NOT EXISTS pgcrypto;      -- gen_random_uuid()

-- ============================================================================
-- 1. Enums
-- ============================================================================
DO $$ BEGIN CREATE TYPE role_t        AS ENUM ('engineer','admin');                       EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE doc_type_t    AS ENUM ('manual','sop','report');                  EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE severity_t    AS ENUM ('info','warning','high','critical');       EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE query_class_t AS ENUM ('knowledge','live_status','action');       EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE msg_role_t    AS ENUM ('user','assistant','agent_event');         EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE verdict_t     AS ENUM ('up','down','fixed');                      EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE author_t      AS ENUM ('system','human');                         EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE pending_t     AS ENUM ('pending','approved','rejected');          EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE wo_status_t   AS ENUM ('draft','open','in_progress','completed','cancelled'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ============================================================================
-- 2. Core domain tables
-- ============================================================================
CREATE TABLE IF NOT EXISTS profiles (
    id          uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    full_name   text,
    role        role_t NOT NULL DEFAULT 'engineer',
    area        text
);

CREATE TABLE IF NOT EXISTS equipment (
    id          text PRIMARY KEY,
    name        text NOT NULL,
    zone        text,
    criticality int  CHECK (criticality BETWEEN 1 AND 10),
    photo_url   text,
    thresholds  jsonb DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS sensor_readings (
    id            bigserial PRIMARY KEY,
    equipment_id  text REFERENCES equipment(id) ON DELETE CASCADE,
    ts            timestamptz NOT NULL,
    vibration_de  real, vibration_nde real, bearing_temp real,
    motor_current real, rpm real, load_pct real
);
CREATE INDEX IF NOT EXISTS idx_sensor_eq_ts ON sensor_readings(equipment_id, ts DESC);

CREATE TABLE IF NOT EXISTS equipment_health (
    equipment_id         text PRIMARY KEY REFERENCES equipment(id) ON DELETE CASCADE,
    computed_at          timestamptz NOT NULL DEFAULT now(),
    anomaly_score        real,
    is_anomalous         boolean,
    rul_days             real,
    rul_band             jsonb,
    contributing_sensors jsonb
);

CREATE TABLE IF NOT EXISTS alerts (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    equipment_id text REFERENCES equipment(id) ON DELETE CASCADE,
    severity     severity_t NOT NULL,
    title        text NOT NULL,
    detail       jsonb DEFAULT '{}'::jsonb,
    target_role  role_t,
    created_at   timestamptz NOT NULL DEFAULT now(),
    acked_by     uuid REFERENCES auth.users(id),
    acked_at     timestamptz
);

CREATE TABLE IF NOT EXISTS breakdown_history (
    id           text PRIMARY KEY,
    equipment_id text REFERENCES equipment(id) ON DELETE CASCADE,
    occurred_at  date,
    fault_code   text,
    symptoms     text,
    root_cause   text,
    resolution   text,
    downtime_hrs real,
    verified     boolean DEFAULT false
);

CREATE TABLE IF NOT EXISTS spares (
    part_no        text PRIMARY KEY,
    equipment_id   text REFERENCES equipment(id) ON DELETE CASCADE,
    description    text,
    stock_qty      int,
    lead_time_days int,
    supplier       text,
    unit_cost_inr  int DEFAULT 0
);
ALTER TABLE spares ADD COLUMN IF NOT EXISTS unit_cost_inr int DEFAULT 0;

-- ----------------------------------------------------------------------------
-- doc_chunks — RAG corpus (seeded by data/corpus/seed_corpus.py → corpus_ingest.sql)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS doc_chunks (
    id           bigserial PRIMARY KEY,
    equipment_id text REFERENCES equipment(id) ON DELETE CASCADE,
    doc_type     doc_type_t NOT NULL,
    section_ref  text,
    content      text NOT NULL,
    content_hash text UNIQUE,            -- ON CONFLICT DO NOTHING dedupe
    source       text,
    embedding    vector(768)
);
CREATE INDEX IF NOT EXISTS idx_doc_chunks_hnsw
    ON doc_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_doc_chunks_fts
    ON doc_chunks USING gin (to_tsvector('english', content));
CREATE INDEX IF NOT EXISTS idx_doc_chunks_eq ON doc_chunks(equipment_id);

CREATE TABLE IF NOT EXISTS semantic_cache (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    equipment_id    text,
    query_text      text,
    query_embedding vector(768),
    response_json   jsonb,
    query_class     query_class_t,
    expires_at      timestamptz
);
CREATE INDEX IF NOT EXISTS idx_semcache_hnsw
    ON semantic_cache USING hnsw (query_embedding vector_cosine_ops);

-- ============================================================================
-- 3. Chat persistence (dual: checkpoints = agent memory, chat_messages = UI memory)
-- ============================================================================
CREATE TABLE IF NOT EXISTS chat_sessions (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),  -- = LangGraph thread_id
    user_id      uuid REFERENCES auth.users(id) ON DELETE CASCADE,
    title        text,
    equipment_id text REFERENCES equipment(id),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    is_archived  boolean DEFAULT false
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON chat_sessions(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS chat_messages (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id uuid REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role       msg_role_t NOT NULL,
    content    text,
    card_json  jsonb,
    agent_name text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON chat_messages(session_id, created_at);

-- ============================================================================
-- 4. Feedback · logbook · reports · audit · HITL · quarantine
-- ============================================================================
CREATE TABLE IF NOT EXISTS feedback (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid REFERENCES auth.users(id),
    session_id   uuid REFERENCES chat_sessions(id) ON DELETE CASCADE,
    message_id   uuid REFERENCES chat_messages(id) ON DELETE CASCADE,
    verdict      verdict_t NOT NULL,
    note         text,
    equipment_id text,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS logbook (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    equipment_id text REFERENCES equipment(id) ON DELETE CASCADE,
    author_type  author_t NOT NULL,
    author_id    uuid,
    entry_type   text,
    content      jsonb,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS reports (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    type         text,
    equipment_id text,
    generated_by uuid,
    pdf_path     text,
    summary      text,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_log (
    id         bigserial PRIMARY KEY,
    user_id    uuid,
    agent_name text,
    action     text,
    resource   text,
    allowed    boolean,
    reason     text,
    detail     jsonb DEFAULT '{}'::jsonb,
    ts         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts DESC);

-- LLM observability: per-call token usage (admin token-usage monitor) + response cache.
CREATE TABLE IF NOT EXISTS llm_usage (
    id                bigserial PRIMARY KEY,
    backend           text,            -- 'ollama' | 'hosted'
    model             text,
    call_type         text,            -- 'classify' | 'synthesize' | 'repair'
    prompt_tokens     int  DEFAULT 0,
    completion_tokens int  DEFAULT 0,
    total_tokens      int  DEFAULT 0,
    cached            boolean DEFAULT false,
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_llm_usage_ts ON llm_usage(created_at DESC);

CREATE TABLE IF NOT EXISTS llm_cache (
    cache_key   text PRIMARY KEY,      -- sha256(backend|model|system|user)
    response    jsonb NOT NULL,
    model       text,
    call_type   text,
    hits        int NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now(),
    last_hit_at timestamptz
);

CREATE TABLE IF NOT EXISTS pending_actions (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id uuid REFERENCES chat_sessions(id) ON DELETE CASCADE,
    proposal   jsonb,
    status     pending_t NOT NULL DEFAULT 'pending',
    decided_by uuid,
    decided_at timestamptz
);

CREATE TABLE IF NOT EXISTS rejected_readings (
    id     bigserial PRIMARY KEY,
    raw    jsonb,
    reason text,
    ts     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS work_orders (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    equipment_id text REFERENCES equipment(id) ON DELETE CASCADE,
    alert_id     uuid REFERENCES alerts(id) ON DELETE SET NULL,
    session_id   uuid REFERENCES chat_sessions(id) ON DELETE SET NULL,
    title        text NOT NULL,
    description  text,
    status       wo_status_t NOT NULL DEFAULT 'open',
    priority     int CHECK (priority BETWEEN 1 AND 100),
    assignee     uuid REFERENCES auth.users(id),
    steps        jsonb DEFAULT '[]'::jsonb,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);
CREATE INDEX IF NOT EXISTS idx_work_orders_eq ON work_orders(equipment_id, status);
CREATE INDEX IF NOT EXISTS idx_work_orders_status ON work_orders(status, created_at DESC);

-- ============================================================================
-- 5. Analytics — read-only curated views (text-to-SQL reaches ONLY these; Phase 7)
-- ============================================================================
CREATE OR REPLACE VIEW v_breakdown_stats AS
    SELECT equipment_id, fault_code, count(*) AS occurrences,
           round(avg(downtime_hrs)::numeric, 2) AS avg_downtime_hrs,
           max(occurred_at) AS last_seen
    FROM breakdown_history GROUP BY equipment_id, fault_code;

CREATE OR REPLACE VIEW v_spares_status AS
    SELECT s.part_no, s.equipment_id, e.name AS equipment_name, s.description,
           s.stock_qty, s.lead_time_days, s.supplier, s.unit_cost_inr
    FROM spares s LEFT JOIN equipment e ON e.id = s.equipment_id;

CREATE OR REPLACE VIEW v_alert_feed AS
    SELECT a.id, a.equipment_id, e.name AS equipment_name, a.severity, a.title,
           a.target_role, a.created_at, (a.acked_at IS NOT NULL) AS acknowledged
    FROM alerts a LEFT JOIN equipment e ON e.id = a.equipment_id;

CREATE OR REPLACE VIEW v_downtime_by_equipment AS
    SELECT b.equipment_id, e.name AS equipment_name,
           round(sum(b.downtime_hrs)::numeric, 1) AS total_downtime_hrs,
           count(*) AS breakdowns
    FROM breakdown_history b LEFT JOIN equipment e ON e.id = b.equipment_id
    GROUP BY b.equipment_id, e.name;

-- ============================================================================
-- 6. SELECT-only analytics role (structurally incapable of writing — §1.7b)
-- ============================================================================
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'forgesight_analyst') THEN
        CREATE ROLE forgesight_analyst NOLOGIN;
    END IF;
END $$;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM forgesight_analyst;
GRANT USAGE ON SCHEMA public TO forgesight_analyst;
GRANT SELECT ON v_breakdown_stats, v_spares_status, v_alert_feed, v_downtime_by_equipment
    TO forgesight_analyst;

-- ============================================================================
-- 7. Row-Level Security (sessions/messages scoped to auth.uid(); admin reads all)
-- ============================================================================
ALTER TABLE chat_sessions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages  ENABLE ROW LEVEL SECURITY;
ALTER TABLE feedback       ENABLE ROW LEVEL SECURITY;
ALTER TABLE profiles       ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS sessions_owner ON chat_sessions;
CREATE POLICY sessions_owner ON chat_sessions FOR ALL
    USING (user_id = auth.uid()
           OR EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'admin'));

DROP POLICY IF EXISTS messages_owner ON chat_messages;
CREATE POLICY messages_owner ON chat_messages FOR ALL
    USING (EXISTS (SELECT 1 FROM chat_sessions s
                   WHERE s.id = chat_messages.session_id
                     AND (s.user_id = auth.uid()
                          OR EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'admin'))));

DROP POLICY IF EXISTS feedback_owner ON feedback;
CREATE POLICY feedback_owner ON feedback FOR ALL USING (user_id = auth.uid());

DROP POLICY IF EXISTS profiles_self ON profiles;
CREATE POLICY profiles_self ON profiles FOR SELECT
    USING (id = auth.uid()
           OR EXISTS (SELECT 1 FROM profiles p WHERE p.id = auth.uid() AND p.role = 'admin'));

-- Reference/operational tables (equipment, sensors, docs, alerts, breakdowns, spares) are
-- readable by any authenticated user; writes happen via the service-role key on the server.
-- audit_log is insert-only via service role (no client policy → no client access).
