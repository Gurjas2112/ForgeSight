# ForgeSight — Intelligent Maintenance Wizard for Steel Plants
### Tata Steel AI Hackathon 2026 · governed, citation-grounded multi-agent maintenance decision-support

ForgeSight turns a fault code into an **auditable fix plan in ~90 seconds**: every answer is cited to
a manual / record / trend, every priority score is deterministic, and every agent runs under an
explicit charter with budgets and human-approval gates — capable of running **fully on-premise** on a
fine-tuned open-source SLM (no plant data needs to leave the network).

> **Author:** Gurjas Singh Gandhi · Software Engineer · Pune, Maharashtra, India

---

## 🔗 Live demo & links

| | |
|---|---|
| 🌐 **Live app (Vercel)** | **https://forge-sight-one.vercel.app** |
| ⚙️ **Backend API (Railway)** | https://forgesight-production.up.railway.app · [project](https://railway.com/project/7f6d4bd2-3cf9-438b-9c84-69353775344d) |
| 💻 **Source (GitHub)** | https://github.com/Gurjas2112/ForgeSight |
| 📹 **Demo video / submission (Google Drive)** | **https://drive.google.com/file/d/1_cvKuAnfQ_ug0OQ9_8_KIiTLRUVjVhCo/view?usp=sharing** |
| 🖼️ **Slide deck** | [`ForgeSight_Submission.pptx`](ForgeSight_Submission.pptx) |

**Demo logins** (seeded, pre-confirmed):

| Role | Email | Password |
|---|---|---|
| Engineer | `engineer@demo.forgesight` | `forgesight-demo` |
| Admin | `admin@demo.forgesight` | `forgesight-demo` |

> Try it: land → log in → **Plant Overview** → open the F3 tile → ask the copilot *"diagnose the F3 trip"* → inspect the **Evidence** drawer. Or open the **3D Digital Twin** and click an asset.

---

## What it does

ForgeSight is an equipment-centric copilot with a **governed multi-agent** core. An engineer (or an
alert) enters the system; a LangGraph controller authorizes the request, classifies intent, routes to
chartered agents that run **deterministic tool pipelines** (RAG · ML · governed SQL), and a small
language model synthesizes a **typed, cited card** — which guardrails validate before it reaches the
engineer. COMMIT actions pause for human approval, and engineer feedback measurably improves future
answers.

**The differentiator is trust:** citations-or-refuse, deterministic scoring, audited authority, and
human-in-the-loop — so a judge (or a plant) can verify *why* every recommendation was made.

---

## ✨ Features

### Governed AI copilot (5 chartered agents)
| Agent | Output card | Tools (deterministic order) |
|---|---|---|
| **Diagnostic** | ranked root-cause + checklist/SOP | `retrieve_rag` → `match_history` |
| **Reliability** | RUL estimate, risk, wait-assessment | `check_equipment_health` → `estimate_rul` |
| **Supervisor** | priority score (factor breakdown) | `score_priority` (rule-based) |
| **Planner** | spares & procurement proposal (HITL) | `check_spares` → `procurement_rule` |
| **Analyst** | governed text-to-SQL result | `query_records` (SELECT-only, curated views) |

- **Cite-or-refuse** — a code-level guardrail makes a fabricated citation structurally impossible.
- **Evidence drawer** — every citation chip resolves to the exact source excerpt (`/evidence`).
- **HITL** — COMMIT actions (e.g. reserve a spare) require explicit engineer approval; every
  allow/deny is timestamped in the audit log.
- **Feedback loop (FR-6)** — 👍/👎/"this fixed it" re-ranks retrieval, injects engineer-verified
  exemplars, and flips records to verified.
- **Global copilot widget** — a fixed-position, fixed-height floating copilot available on every page;
  the conversation scrolls internally (the page never grows). Per-user **conversation history with
  timestamps** is persisted server-side and restorable from a history switcher (`GET /chat/sessions`).

### Dashboard modules (live backend data)
Tabbed within the dashboard so the **Overview → equipment → copilot** workflow stays intact:

- **3D Digital Twin** — plant zones & assets in three.js (react-three-fiber), color-coded by health;
  click an asset to inspect RUL, maintenance status & open work orders.
- **Evidence** — unified search across manuals, SOPs, incidents, sensor events, work orders & spares.
- **Work Orders** — status tracking, JSON/PDF export, maintenance execution flow.
- **Incidents** — replay: production impact, failure progression, corrective action, lessons learned.
- **Spares** — catalog cards (stock, cost, lead time, linked asset, PO action) + **inventory
  optimizer** (shortage risk & production exposure).
- **Reliability** — predictive curves, failure probability, RUL forecast, trend analysis.
- **Leadership** — shutdown vs potential-failure cost, expected savings, ROI, confidence,
  recommended action.
- **Admin** (admin-only) — a system-metrics console: accounts by role, conversations & messages,
  knowledge-corpus size, work orders by status, governance-audit activity (24h), open alerts, plant
  availability and feedback — every value a live DB aggregate (`GET /admin/metrics`), plus the live
  model scorecard, an accounts roster and a recent-audit feed. Also an **LLM token-usage monitor**:
  prompt/completion/total tokens, a 14-day token chart, per-call-type breakdown, estimated cost, and
  **cache hit-rate** — backed by a persistent LLM response cache (`llm_cache`) that serves repeat
  query+evidence for 0 tokens, and a per-call meter (`llm_usage`).

### Prediction & alerting
- **Real-time scheduler** re-scans equipment health → raises severity-ranked alerts (`/alerts`).
- **Anomaly** (IsolationForest + EWMA), **RUL** (trend + XGBoost C-MAPSS), early-warning gate
  (CRITICAL when RUL < spares lead time).
- **PDF reports** (ReportLab) — abnormal-alert report + shift summary.

---

## 🧩 Requirements traceability (PS §6 FR-1..7)

| FR | Requirement | Where |
|---|---|---|
| FR-1 | LLM/SLM contextual reasoning (merit: fine-tune) | `backend/agent/synthesis.py` (Ollama Qwen / Groq), `finetune/` |
| FR-2 | Knowledge integration (manuals/SOPs/records) | `backend/tools/rag.py` + governed `text_to_sql.py` |
| FR-3 | Natural-language, multi-turn | `/chat` + LangGraph checkpointer |
| FR-4 | Explainable & traceable | citation guardrail + Evidence drawer |
| FR-5 | Anomaly · early warning · failure prediction | `ml/*`, scheduler, `/models/scorecard` |
| FR-6 | Feedback-driven improvement | `POST /feedback`, `backend/tools/feedback_store.py` |
| FR-7 | Real-time alerting | `backend/scheduler/health_scan.py` → `/alerts` |

Full mapping: [`docs/requirements_traceability.md`](docs/requirements_traceability.md).

---

## 🏗️ Architecture

**Three governed layers over a vector-enabled store:**

- **Frontend** (Next.js 16 · React 19 · Vercel) — landing, role-based auth, dashboard tabs,
  equipment console, 3D digital twin.
- **Backend** (FastAPI · Railway · Docker) — LangGraph `AgentController`, `AgentAuthority`,
  `AgentGuardrails`, tools, scheduler.
- **Data** (Supabase · Postgres + pgvector) — equipment, sensors, health, alerts, breakdowns,
  `doc_chunks`, spares, `work_orders`, RLS.

The controller runs `ingest_and_authorize → cache_lookup → classify_intent →` charter-scoped agent
pipelines (deterministic tool sequences, **not** ReAct loops) `→ synthesize → guardrail_validate →
{respond | human_gate | repair | degrade}`. The SLM (constrained JSON decoding) is invoked **only**
at synthesize/repair — it narrates and fills schemas; it never selects tools or computes numbers.

Diagrams (PlantUML source + rendered PNG) in [`generated_app_diagrams/`](generated_app_diagrams/):
Backend Architecture · RAG/Knowledge Ingestion · Multi-Agent Workflow · Maintenance Decision
Lifecycle · Feedback-Driven Improvement Loop. Full design: [`docs/architecture.md`](docs/architecture.md).

---

## 🛠️ Technology stack

- **Frontend:** Next.js 16, React 19, TypeScript, Tailwind CSS, react-three-fiber / three.js, Recharts
- **Backend & agents:** FastAPI, Python 3.12, LangGraph, Pydantic, Uvicorn, ReportLab
- **AI / ML:** Qwen2.5-3B via Ollama (on-prem) · Groq Llama-3.3-70B (cloud fallback) ·
  nomic-embed-text · scikit-learn · XGBoost · LightGBM · QLoRA (Unsloth)
- **Data & infra:** Supabase (Postgres + pgvector), Railway, Vercel, Docker, GitHub

Links per technology: [`generated_app_diagrams/assets/tech_stack_links.json`](generated_app_diagrams/assets/tech_stack_links.json).

---

## 🤖 ML models

Each model ships a Kaggle-style `test.csv` → `submission.csv` and is surfaced as a **live held-out
inference** via `GET /models/scorecard`. See [`ml/Ml_workflow.md`](ml/Ml_workflow.md).

| Model | Dataset | Algorithm | Headline metric |
|---|---|---|---|
| anomaly | synthetic steel sensors | IsolationForest + EWMA | recall 1.0 · 8.7 d lead |
| failure_classifier | AI4I 2020 | XGBoost | recall 0.91 · PR-AUC 0.80 |
| rul | NASA C-MAPSS FD001 | XGBoost (by-unit split) | RMSE ≈ 16–19 cycles |
| defect | UCI Steel Plates | LightGBM (leakage-safe) | PR-AUC 0.80 |
| azure_pdm | Azure PdM | XGBoost (24h-ahead) | PR-AUC 0.90 · recall 0.92 |

**Fine-tune (hybrid serving):** QLoRA on Qwen2.5-3B (Unsloth, Colab T4) → GGUF → `ollama create
qwen-forgesight`. The exported GGUF (`finetune/export/qwen-forgesight.Q4_K_M.gguf`) is **verified
deployable** locally — `ollama create` + a JSON smoke prompt succeed — and is promoted
(`OLLAMA_MODEL=qwen-forgesight`) only if it beats base on citation compliance + number fidelity. On-prem
serves the fine-tuned model; the public demo uses the Groq fallback (Railway has no GPU). Base Qwen is
the gated, safe default. See [`finetune/finetuning_workflow.md`](finetune/finetuning_workflow.md).

---

## 📂 Repository structure

```
backend/      FastAPI app · agent graph (governance, pipelines, synthesis) · tools · db · scheduler · tests
frontend/     Next.js 16 app (dashboard tabs, equipment console, 3D twin, copilot) + lib/api + components
ml/           5 models (anomaly · failure_classifier · rul · defect · azure_pdm) + bearing_features
finetune/     QLoRA SFT dataset + quality gates + Colab T4 runner + Modelfile
data/         dataset fetchers · synthetic sensor + corpus generators · raw/
docs/         architecture · requirements_traceability · assumptions_limitations · DEPLOY · finetune · demo_script
scripts/      diagnose_f3 · screenshot agents (Playwright)
generated_app_images/      live UI screenshots (used in the deck)
generated_app_diagrams/    PlantUML sources + rendered diagrams + assets (logo, tech links)
system_ppt_doc_conversion.py   submission-deck generator  →  ForgeSight_Submission.pptx
```

---

## ⚡ Install · Configure · Run (local)

**Prerequisites:** Python 3.12 + [uv](https://github.com/astral-sh/uv); [Ollama](https://ollama.com);
a Supabase project (Postgres + pgvector) **or** a local pgvector container.

```bash
cp .env.example .env            # fill DATABASE_URL + keys
uv sync                          # backend + ml deps
ollama pull qwen2.5:3b-instruct && ollama pull nomic-embed-text

# 1 · datasets + corpus
uv run python data/fetch_data.py
uv run python data/synthetic/generate_sensors.py
uv run python data/corpus/seed_corpus.py --pdf-dir data/synthetic/manuals --out-sql data/corpus/corpus_ingest.sql

# 2 · classical ML  → artifacts to backend/models/
uv run python ml/anomaly/train.py
uv run python ml/failure_classifier/train.py
uv run python ml/rul/train.py
uv run python ml/defect/train.py
uv run python ml/azure_pdm/train.py
uv run python ml/bearing_features/extract_features.py
uv run python -m backend.tools.build_scorecard

# 3 · (optional) fine-tune the SLM — GPU step on Colab T4
uv run python finetune/dataset/generate_sft.py && uv run python finetune/dataset/quality_gates.py

# 4 · database (Supabase, or a local pgvector container)
uv run python backend/db/apply_migrations.py          # schema + RLS + seeds + corpus + work_orders + spares
uv run python backend/scheduler/health_scan.py --once # populate equipment_health + the CRITICAL alert

# 5 · run
uv run uvicorn backend.server:app --port 8000         # backend  (terminal 1)
cd frontend && npm install && npm run dev             # http://localhost:3000  (terminal 2)
```

Open **localhost:3000**, log in with a demo account, and follow the flow above. See
[`docs/demo_script.md`](docs/demo_script.md) for the full recording choreography.

### Configuration (`.env`)
Key settings (see `.env.example`): `DATABASE_URL`, `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` /
`SUPABASE_JWT_SECRET`, `SYNTHESIS_BACKEND` (`ollama` | `hosted`), `LLM_PROVIDER` (`groq` | `openai`)
+ `LLM_API_KEY`, `OLLAMA_MODEL`, `ENABLE_SCHEDULER`, `ALLOWED_ORIGINS`. The frontend reads
`NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`.

---

## 🚀 Deploy

- **Backend → Railway** (Docker, `backend/Dockerfile`, `railway.json`): set secrets (`DATABASE_URL`,
  `SUPABASE_*`, `SYNTHESIS_BACKEND=hosted`, `LLM_PROVIDER=groq`, `LLM_API_KEY`, `ALLOWED_ORIGINS`),
  run `backend/db/apply_migrations.py` against the DB, then `railway up`.
- **DB → Supabase** (Postgres + pgvector) — `CREATE EXTENSION vector`, RLS, seeds applied by the
  migration runner.
- **Frontend → Vercel** (`vercel --prod`; root directory `frontend`, `.vercelignore` keeps the heavy
  ML/data trees out of the upload). Set `NEXT_PUBLIC_API_URL` + Supabase envs.

Full steps & verification: [`docs/DEPLOY.md`](docs/DEPLOY.md).

---

## ✅ Testing & verification

```bash
uv run pytest backend/tests -q     # 40 passing — deterministic tools, guardrails, feedback loop,
                                   # prompt builder, plant-summary, auth gating, per-turn budget
cd frontend && npx tsc --noEmit && npx next build
```

`scripts/diagnose_f3.py` reproduces a DiagnosisCard citing `BR-2024-0312`. The live deployment is
verified in [`docs/verification_report.md`](docs/verification_report.md).

---

## ⚠️ Assumptions & limitations (honest framing)

- **Digital twin** — the sensor stream is a physics-shaped **simulation** (no public steel-plant
  feed); the governance, ML inference and reasoning that run on top of it are real.
- **Benchmark models** — failure/RUL/defect/PdM validate the *method* on public datasets; they are
  benchmark second-opinions, not per-asset sensor models.
- **Cloud serving** — the public demo runs Groq (no GPU) + full-text-primary retrieval; on-prem runs
  the fine-tuned Qwen via Ollama. `/healthz` reports the active backend + model.
- **Costs/ROI** — downtime-at-risk uses a documented ₹/hr × criticality assumption, returned with
  every figure.

Details: [`docs/assumptions_limitations.md`](docs/assumptions_limitations.md).

---

## 🔐 Security

Secrets live only in `.env` (gitignored); `.env.example` is the redacted template. Any credential
that appeared in earlier drafts (`SUPABASE_JWT_SECRET`, `SUPABASE_SERVICE_ROLE_KEY`,
`SUPABASE_ANON_KEY`, API keys) should be treated as **compromised and rotated** before real use.
Public signup is **engineer-only**; admin accounts are provisioned by an administrator, and a
self-assigned admin request is downgraded and audited. Signup is validated on both client and server
(RFC email via pydantic `EmailStr`; password ≥8 chars with a letter + a number; duplicate emails return
a clean 409). Backend JWT verification is the enforced boundary on every request; chat-session reads are
filtered to the owner (admins excepted). Email-confirmation (SMTP) is deferred — demo accounts are
pre-confirmed.

---

## 📦 Submission artifacts

- **Slide deck:** [`ForgeSight_Submission.pptx`](ForgeSight_Submission.pptx) (generated by
  `system_ppt_doc_conversion.py`)
- **Architecture diagrams:** [`generated_app_diagrams/`](generated_app_diagrams/) (PlantUML + PNG)
- **UI screenshots:** [`generated_app_images/`](generated_app_images/)
- **Demo video:** [Google Drive](https://drive.google.com/file/d/1_cvKuAnfQ_ug0OQ9_8_KIiTLRUVjVhCo/view?usp=sharing)

---

<div align="center">

**ForgeSight** — governed, explainable maintenance intelligence for steel plants
Gurjas Singh Gandhi · Tata Steel AI Hackathon 2026

</div>
