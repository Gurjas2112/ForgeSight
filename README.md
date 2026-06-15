# ForgeSight — Intelligent Maintenance Wizard for Steel Plants
### Tata Steel AI Hackathon 2026 · governed multi-agent maintenance decision-support

ForgeSight turns a fault code into an auditable fix plan in ~90 seconds: every answer cited to a
manual / record / trend, every priority score deterministic, every agent under an explicit
charter with budgets and human-approval gates — running **fully on-premise** on a fine-tuned
open-source SLM (no plant data leaves the network).

The authoritative design lives in [`forgesight-v3-final.md`](forgesight-v3-final.md); the build
order is [`BUILD_GUIDE.md`](BUILD_GUIDE.md).

---

## ⚠️ Security: rotate these secrets

`BUILD_GUIDE.md §10` shipped live-looking credentials in plaintext. Treat them as **compromised**
and rotate in the Supabase dashboard before any real deployment:
- `SUPABASE_JWT_SECRET`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`
- `FIRECRAWL_API_KEY`, `KAGGLE_KEY`

Secrets now live only in `.env` (gitignored). `.env.example` is the redacted template.

---

## Build status

This repo is built in passes following `BUILD_GUIDE.md`. **Pass 1 (current)** delivers the
foundation + the Scenario A vertical slice (fault code → cited `DiagnosisCard`):

| Phase | Component | Status |
|---|---|---|
| 1 | Datasets + corpus (`data/`) | ✅ Pass 1 |
| 4 | Supabase schema + RLS (`backend/db/`) | ✅ Pass 1 |
| 4 | Card schemas, RAG + deterministic tools | ✅ Pass 1 |
| 4 | Governed graph — Diagnostic pipeline | ✅ Pass 1 |
| 2 | ML notebooks + artifacts (`ml/`) | ⏳ deferred |
| 3 | SLM fine-tune (`finetune/`) | ⏳ deferred (base Qwen2.5-3B for now) |
| 4 | Reliability / Supervisor / Planner pipelines | ⏳ deferred |
| 5 | Frontend (`frontend/`, Next.js 15 + CopilotKit) | ⏳ deferred |

---

## Prerequisites

- Python 3.12 + [uv](https://github.com/astral-sh/uv)
- [Ollama](https://ollama.com) with models pulled:
  `ollama pull qwen2.5:3b-instruct && ollama pull nomic-embed-text`
- A Supabase project (Postgres + pgvector). Set `DATABASE_URL` in `.env`.

## Run order (full system)

```bash
cp .env.example .env          # then fill DATABASE_URL + keys
uv sync                        # or: uv pip install -r backend/requirements.txt + ml/finetune extras
ollama pull qwen2.5:3b-instruct && ollama pull nomic-embed-text

# 1. Datasets + corpus (Gate 1)
uv run python data/fetch_data.py                      # C-MAPSS / AI4I / Steel Plates → data/raw/
uv run python data/synthetic/generate_sensors.py     # → sensor_readings.csv (~52k rows)
uv run python data/corpus/seed_corpus.py --pdf-dir data/synthetic/manuals \
    --out-sql data/corpus/corpus_ingest.sql          # → corpus_ingest.sql + breakdown_history.json

# 2. Classical ML (Gate 2) — artifacts → backend/models/
uv run python ml/anomaly/train.py
uv run python ml/failure_classifier/train.py
uv run python ml/rul/train.py
uv run python ml/defect/train.py
cp ml/shared/feature_config.json ml/shared/metrics.json backend/models/

# 3. (optional) Fine-tune — runs on Colab/GPU; base Qwen ships otherwise
uv run python finetune/dataset/generate_sft.py && uv run python finetune/dataset/quality_gates.py
#   then finetune/train_qlora.py on Colab → ollama create qwen-forgesight -f finetune/Modelfile

# 4. Database — Supabase (set DATABASE_URL) OR a local pgvector container for an offline demo:
bash scripts/local_pg.sh                              # prints DATABASE_URL for the container
export DATABASE_URL=postgresql://postgres:forgesight@localhost:5433/forgesight
uv run python backend/db/apply_migrations.py          # schema + seeds + corpus + sensors
uv run python backend/scheduler/health_scan.py --once # populate equipment_health + alerts

# 5. Backend API + frontend
uv run uvicorn backend.server:app --port 8000         # graph over HTTP (terminal 1)
cd frontend && npm install && npm run dev             # localhost:3000 (terminal 2)

# Verify (Gate 4): governed graph + tests
uv run python scripts/diagnose_f3.py                  # DiagnosisCard citing BR-2024-0312
uv run pytest backend/tests -q                        # 23 green
```

Open **localhost:3000** → Plant Overview → click the F3 tile → ask the Copilot "diagnose the F3
trip". See `docs/demo_script.md` for the full recording choreography.

## Demo credentials (seeded, pre-confirmed)

| Role | Email | Password |
|---|---|---|
| Engineer | `engineer@demo.forgesight` | `forgesight-demo` |
| Admin | `admin@demo.forgesight` | `forgesight-demo` |

---

## Architecture (one paragraph)

A LangGraph `AgentController` runs `ingest_and_authorize → cache_lookup → classify_intent →`
charter-scoped agent pipelines (deterministic tool sequences, **not** ReAct loops) `→ synthesize
→ guardrail_validate → {respond | human_gate | repair | degrade}`. `AgentAuthority` enforces
per-agent charters / budgets / escalation (audited allow+deny); `AgentGuardrails` enforce
citation-existence, LOTO-first ordering, and matrix-provenance in code. The SLM (Ollama, Qwen2.5,
`format=<schema>` constrained decoding) is invoked **only** at synthesis/repair — it narrates and
fills schemas, it never selects tools or computes numbers. Full design: `forgesight-v3-final.md`.
