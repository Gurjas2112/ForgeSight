# ForgeSight — Tata Steel AI Hackathon 2026 · Final Interview Prep (Q&A)

**Candidate:** Gurjas Singh Gandhi · **Role:** Manager / Area Manager — Artificial Intelligence, Tata Steel
**Milestone:** Top 40 (Round 2 — Agentic AI Challenge) · **Interview:** Fri 26 Jun, 6:50–7:10 PM IST (MS Teams, ~20 min + buffer)
**Project:** ForgeSight — a governed, citation-grounded **multi-agent Maintenance Wizard** for steel plants.

> How to use this doc: **Part 0** (strategy) + **Part 1** (project narrative) + the **90-sec pitch** are must-revise.
> Parts 2–4 are the deep system/coding defense. Parts 5–6 are fundamentals. Part 7 is behavioral. Part 8 is curveballs.
> For a 20-min panel: lead with impact, speak in the "agents propose, humans commit, everything is cited & audited" frame.

---

# Part 0 — Interview Strategy & Logistics

## 0.1 What this role really wants (from the JD)
The JD is a **senior, hands-on AI leader** for **Industry 5.0** (human + machine intelligence). It blends:
- **Build**: Python + DS, classical ML (time-series, optimization, classification, regression), DL (CNN/RNN/LSTM), **GenAI** (Agentic Design, RAG, prompt-to-template, chunking, SLM, fine-tuning).
- **Architect & ship**: decentralized architectures, **PostgreSQL/SQL/NoSQL**, multi-cloud (GCP/AWS/Azure), **serverless** (Cloud Run/Lambda/Functions) + **Kubernetes/GKE**, **MLOps**, **IT-OT**.
- **Lead & communicate**: translate business→technical, manage multiple projects, stakeholder buy-in, **responsible AI**.

**Your edge:** ForgeSight is *exactly* an Agentic + RAG + SLM system on PostgreSQL with MLOps and a real steel-plant business case — you built the thing the JD describes. Round 1 proves the classical-ML/feature-engineering muscle.

## 0.2 JD → ForgeSight competency map (memorize this table)

| JD competency | Where you demonstrate it |
|---|---|
| Agentic Design | LangGraph governed controller, 5 chartered sub-agents, Authority + Guardrails, HITL |
| RAG + chunking strategies | `tools/rag.py` hybrid (pgvector + full-text); structure-aware chunking of real OEM PDFs (ABB/SKF/fan) |
| Prompt-to-template | Constrained-JSON synthesis → **typed cards** (`schemas/cards.py`); SLM fills a schema, never free-text |
| SLM / fine-tuning / pre-training | Qwen2.5-3B via Ollama (on-prem) / Groq (cloud); **QLoRA** fine-tune (`finetune/`) with a promotion rule |
| Classification & regression | Round 1 defect classifier; ForgeSight RUL (regression), anomaly, failure, defect, PdM models |
| Time-series | Anomaly (IsolationForest + EWMA) on sensor streams; RUL on C-MAPSS run-to-failure |
| Optimization | Spares **inventory optimizer**, deterministic priority scoring, threshold optimization (Round 1) |
| LangChain / LangGraph | The whole orchestration core; checkpointer for multi-turn memory |
| PostgreSQL / SQL / NoSQL | Supabase Postgres + **pgvector**, governed text-to-SQL Analyst agent, JSONB cards |
| Serverless / multi-cloud / K8s | Dockerized FastAPI on Railway; Vercel frontend; deploy story maps to Cloud Run/Lambda/GKE |
| MLOps | train→publish→serve parity (`ml/shared/feature_config.json`), model scorecard, token-usage monitor, caching |
| Responsible AI | **cite-or-refuse** guardrail, full **audit_log**, HITL gates, on-prem option (data never leaves the plant) |
| IT-OT | Sensor (OT) → governance/ML/LLM (IT) boundary; honest about the simulated stream |
| Stakeholder communication | Leadership ROI view, structured reports, explainable cited answers |

## 0.3 The 90-second pitch (rehearse out loud)
> "Steel-plant maintenance engineers juggle manuals, SOPs, breakdown logs, and sensor alerts under time pressure. ForgeSight is a **governed multi-agent maintenance copilot** that turns a fault code into an **auditable fix plan in ~90 seconds**. A LangGraph controller authorizes the request, classifies intent, and routes to chartered agents — Diagnostic, Reliability, Supervisor, Planner, Analyst — that run **deterministic tool pipelines**: RAG over real OEM manuals, five ML models for anomaly/RUL/failure/defect prediction, and governed SQL. A small language model then **synthesizes a typed, cited card**, which guardrails validate before it reaches the engineer. The differentiator is **trust**: every answer is cited or it refuses, every number is computed by a tool not the LLM, COMMIT actions need human approval, and every decision is audited. It runs **fully on-prem on a fine-tuned 3B model** so no plant data leaves the network, with a hosted-LLM fallback for the cloud demo. I also added an admin token-usage monitor and an LLM cache so it's cost-aware in production."

## 0.4 20-minute flow (likely)
1–2 min intro → 3–5 min project overview (use the pitch) → 6–10 min deep-dive on **one** area they pick (be ready for Agentic, RAG, or ML) → coding/SQL question → 2–3 fundamentals → behavioral → your questions. **Keep answers 60–90s, then offer to go deeper.**

## 0.5 Questions to ask them
- "How is Tata Steel currently bridging the **IT-OT** gap for predictive maintenance — historian/OPC-UA into the cloud, or edge-first?"
- "Is the AI org standardizing on a single agent framework (LangGraph / **Google ADK**) and one cloud, or staying decentralized per plant?"
- "For GenAI in operations, what's the stance on **on-prem SLMs vs hosted LLMs** given data-sovereignty?"
- "What does success look like in the first 6 months for this role?"

---

# Part 1 — Project Narrative & PS Traceability

## 1.1 The problem statement (Round 2)
Build an **intelligent Maintenance Wizard** for steel equipment that ingests fragmented inputs (delay logs, fault messages, failure reports, sensor summaries, manuals, SOPs, spares) and produces **explainable, actionable** outputs: fault diagnosis, **root-cause analysis**, **RUL prediction**, early warning of catastrophic failure, **risk/priority** classification, step-by-step recommendations, spares strategy, and structured reports — with **NL multi-turn chat**, a **feedback loop**, and **real-time alerting**.

## 1.2 FR → implementation matrix (defensible, file-level)

| FR | Requirement | ForgeSight implementation |
|---|---|---|
| FR-1 | LLM/SLM contextual reasoning (merit: fine-tune) | `agent/synthesis.py` (Ollama Qwen-3B / Groq), `finetune/` QLoRA |
| FR-2 | Knowledge integration (manuals/SOPs/records) | `tools/rag.py` over `doc_chunks` + governed `text_to_sql.py` |
| FR-3 | NL, multi-turn | `POST /chat` + LangGraph checkpointer (thread_id = session_id) |
| FR-4 | Explainable & traceable | cite-or-refuse guardrail + Evidence drawer (`/evidence`) |
| FR-5 | Anomaly · early warning · failure prediction | `ml/*` + `scheduler/health_scan.py` + `/models/scorecard` |
| FR-6 | Feedback-driven improvement | `POST /feedback` → re-rank retrieval, verified exemplars |
| FR-7 | Real-time alerting | scheduler re-scans health → `alerts` table → `/alerts` |

**Expected outputs → typed cards** (`schemas/cards.py`): `diagnosis`, `checklist`, `rul`, `risk`, `wait_assessment`, `priority`, `spares`, `sql` (analytical), plus honest-failure cards `degraded` / `no_evidence`.

## 1.3 Canonical scenario — "diagnose the F3 trip" (walk this end-to-end)
1. Engineer opens the **F3 caster** page and asks *"diagnose the F3 trip"* (or an alert fires).
2. `POST /chat` → controller **ingest_and_authorize** (verify Supabase JWT → `AuthUser{role}`; create the `chat_sessions` row; log the user message).
3. **cache_lookup** — exact/semantic cache + golden-demo fallback.
4. **classify_intent** — knowledge / live_status / action; pick the agent.
5. **Diagnostic agent** runs a *fixed* pipeline: `retrieve_rag` (hybrid search over OEM manual + SOP chunks) → `match_history` (similar past breakdowns). Tools return **evidence + citation refs**.
6. **synthesize** — the SLM is handed `TOOL_RESULTS` + `CITATIONS` and emits a **JSON diagnosis card** (ranked root causes, confidence, recommended next, citation_refs) under constrained decoding.
7. **guardrail_validate** — schema valid? every `citation_ref` ∈ provided CITATIONS? safety/LOTO first? If a COMMIT (e.g., reserve a spare) → **human_gate** (pause for approval). If broken → **repair** (one retry) → else **degrade** (honest no_evidence card).
8. **respond** — persist the assistant card + agent_event rows (timestamps); return `{card, delegations, citations}`. Frontend renders the card; each citation chip opens the **Evidence drawer** showing the exact manual excerpt.
9. Engineer clicks **👍/👎/"this fixed it"** → `POST /feedback` re-ranks retrieval and flips the matching breakdown record to engineer-verified (FR-6).

**One-liner:** *Sensors and documents in → governed reasoning → a typed, cited, audited fix plan out, with a human in the loop for anything that changes plant state.*

---

# Part 2 — System Design (Scenario-Based) Q&A

### Q1. Walk me through your architecture.
**A.** Three governed layers over a vector-enabled store:
- **Frontend** (Next.js 16/React 19 on Vercel): landing, role-based auth, dashboard tabs, 3D digital twin, global copilot widget.
- **Backend** (FastAPI on Railway, Docker): a **LangGraph `AgentController`** wrapping `AgentAuthority` (charters/budgets/audit), `AgentGuardrails` (citation + schema checks), chartered sub-agents with deterministic tool pipelines, the SLM synthesizer, caches, and the health scheduler.
- **Data** (Supabase Postgres + **pgvector**): equipment, sensor_readings, equipment_health, alerts, breakdown_history, spares, **doc_chunks** (RAG), chat_sessions/messages, audit_log, work_orders, llm_usage/llm_cache.

The controller path is `ingest_and_authorize → cache_lookup → classify_intent → <agent pipeline> → synthesize → guardrail_validate → {respond | human_gate | repair | degrade}`. The **LLM is called only at synthesize/repair** — it narrates and fills schemas; it never picks tools or computes numbers.

### Q2. Why a *governed* multi-agent design and not a ReAct agent that calls tools freely?
**A.** In a safety-critical plant, an autonomous tool-looping agent is unpredictable and hard to audit. I made each agent a **chartered specialist with a fixed, deterministic tool sequence** (e.g., Diagnostic = retrieve_rag → match_history). Benefits: **reproducibility** (same inputs → same tool calls), **auditability** (every Authority allow/deny is logged), **bounded cost** (per-turn budget, no infinite loops), and **safety** (COMMIT actions pause for humans). The LLM's only job is language, not control flow — so it can't "decide" to do something dangerous. That's the trust story Tata Steel ops would need.

### Q3. How does RAG work, and what chunking strategy did you use?
**A.** I ingest **real OEM PDFs** (ABB ACS880 VFD manual, SKF bearing handbook, centrifugal-fan O&M) with PyMuPDF, using **structure-aware chunking**: section headers become chunks and **fault tables become one chunk per fault code** (so a fault-code query retrieves the precise row, not a whole page). Each chunk is tagged `doc_type ∈ {manual, sop, report}` with a stable `section_ref` used as the citation. Retrieval is **hybrid**: pgvector cosine similarity (nomic-embed-text, 768-dim, HNSW index) **+** Postgres full-text (`tsvector`), fused. In the cloud demo (no Ollama for embeddings) it **degrades to full-text-primary** (`RETRIEVAL_MODE=fulltext`) so it still works. Chunking strategy matters because over-large chunks dilute relevance and over-small chunks lose context — fault tables are the exception where row-level is exactly right.

### Q4. RAG vs fine-tuning vs prompt engineering — when each?
**A.** **RAG** for knowledge that changes or must be cited (manuals, SOPs, live records) — it's the source of truth and gives traceability. **Fine-tuning** for *behavior/format* — I fine-tuned Qwen-3B (QLoRA) to reliably emit the **cited JSON card format** and copy numbers verbatim, not to memorize facts. **Prompt engineering / constrained decoding** for structure and guardrails. They're complementary: RAG supplies facts, fine-tune/constrained-decoding supplies the disciplined output shape. I explicitly *don't* fine-tune knowledge in — that would hurt traceability and go stale.

### Q5. How does the SLM avoid hallucinating numbers or citations?
**A.** Three mechanisms: (1) **Tools compute, LLM narrates** — RUL/anomaly/priority come from ML/SQL; the LLM is told to copy them verbatim. (2) **Constrained JSON decoding** to a Pydantic schema (prompt-to-template) so output is always a valid typed card. (3) **Cite-or-refuse guardrail**: after synthesis I check every `citation_ref` is in the CITATIONS actually retrieved; if the model cites something not provided, the card is rejected → one repair attempt → else an honest `no_evidence` card. So a fabricated citation is *structurally* impossible to surface.

### Q6. Fine-tuning details and your promotion rule?
**A.** **QLoRA via Unsloth** on Qwen2.5-3B (LoRA r=16, 4-bit), trained on Colab T4. The SFT pairs are generated by running the **real backend tools** over the seeded corpus (so labels are grounded in actual evidence), then passed through **quality gates** (valid JSON, schema match, citations ⊆ provided, LOTO-first). Export → GGUF (Q4_K_M) for Ollama. **Promotion rule:** ship the fine-tune *only if* it beats base Qwen on **citation compliance AND number fidelity** (`03_evaluate_vs_base.py`); otherwise base ships, because citation compliance is already structural via constrained decoding. I verified the GGUF loads and serves locally via Ollama. Production keeps the hosted Groq path because Railway has no GPU.

### Q7. Multi-turn memory?
**A.** Dual memory: **LangGraph checkpointer** (Postgres) keyed by `thread_id = session_id` holds agent state for resumes/HITL; **chat_messages** holds the UI-visible transcript (user + assistant + agent_event rows with timestamps). The copilot lists a user's past sessions and restores them. RLS plus explicit `user_id` filtering keeps sessions private.

### Q8. Real-time alerting & early warning?
**A.** A background scheduler (`scheduler/health_scan.py`) re-scans equipment health every N seconds: the anomaly model scores live sensor windows, RUL is estimated, and an **early-warning gate** raises a **CRITICAL** alert when `RUL < spares lead time` (you'll fail before the part arrives). Alerts land in the `alerts` table and surface at `/alerts` and on the dashboard.

### Q9. Caching & cost control (token-usage monitor)?
**A.** Two layers. **`llm_cache`** is an exact-match response cache keyed by `sha256(backend|model|system|user)` — a hit returns the prior card for **0 tokens**. **`semantic_cache`** (pgvector) matches near-duplicate queries by embedding. Every LLM call writes a row to **`llm_usage`** (backend, model, call_type, prompt/completion/total tokens, `cached` flag), which powers an **admin token-usage monitor**: total tokens, **cache hit-rate**, estimated cost, a 14-day token chart, and a per-call-type breakdown. This is the MLOps/cost-governance story.

### Q10. Scaling & decentralized / IT-OT architecture?
**A.** Stateless FastAPI behind a load balancer scales horizontally; Postgres + pgvector scales reads via replicas; the SLM is the bottleneck so it sits behind the cache and can run per-plant (decentralized) on local GPUs. **IT-OT**: the OT side (PLCs/historian/sensors) feeds summarized readings across the boundary into the IT side (governance + ML + LLM) — I never let the LLM touch control systems; agents *propose*, humans *commit*. On-prem SLM means **data sovereignty** (nothing leaves the plant network).

### Q11. How would you deploy this on Tata Steel's cloud (GCP/AWS/Azure, serverless, K8s)?
**A.** Containerize the API (already Dockerized). For bursty traffic, **Cloud Run / AWS Lambda (container) / Azure Container Apps** gives serverless autoscaling; for steady load and GPU SLM serving, **GKE/EKS/AKS** with a model-serving deployment (vLLM/Ollama) and an HPA. Postgres → **Cloud SQL / RDS / Azure DB for PostgreSQL** with pgvector. Embeddings/LLM either a managed endpoint or in-cluster. CI/CD via GitHub Actions → registry → rolling deploy; secrets in the cloud secret manager; observability via the token monitor + tracing. The codebase is cloud-agnostic (12-factor, env-driven config) so it ports cleanly.

### Q12. Responsible AI?
**A.** **Explainability** (cite-or-refuse + evidence drawer), **auditability** (every authority decision logged), **human-in-the-loop** for state changes, **privacy** (on-prem option; secrets gitignored; RLS), and **honest failure** (it says "no evidence" rather than guessing). For bias: the ML models are validated on public benchmarks with PR-AUC/recall (not accuracy) given imbalance, and the feedback loop lets engineers correct the system over time.

---

# Part 3 — Code-Wise Workflow (Explain Every Module)

> Format per module: **what it is → key pieces → likely question.** Use these as your "tour" if asked "walk me through the code."

## 3.1 `backend/server.py` — the HTTP surface
FastAPI app; `lifespan` builds the controller **once** (caches armed) and starts the scheduler. Auth helpers: `current_user()` (verify Supabase JWT → `AuthUser`), `require_admin()`. Routes: `POST /chat`, `POST /chat/approve` (resume HITL), `GET /chat/sessions[/{id}/messages]`, `POST /auth/signup` (validated `EmailStr` + password rules), `GET /equipment[...]`, `/alerts`, `/plant/summary`, `/models/scorecard`, `/search`, `/work-orders`, `/incidents`, `/spares`, `/inventory/optimizer`, `/reliability`, `/leadership/roi`, `/feedback`, `/reports/*`, and admin `/admin/metrics|users|audit|llm-usage`.
- *Likely Q:* "How do you stop public users self-assigning admin?" → signup is engineer-only; an `admin` request from a non-admin is downgraded and **audited**; `require_admin` gates admin routes; the backend uses the service-role pool so per-user filtering is explicit in SQL.

## 3.2 `backend/agent/build.py` — controller wiring
`build_controller(pool, persistence, demo_cache)` assembles the LangGraph graph: Authority + Guardrails + agent pipelines + SLM synthesizer + caches + persistence into a single `invoke`-able controller.
- *Likely Q:* "Where's the orchestration?" → here; nodes are wired as a graph, edges encode the governed flow.

## 3.3 `backend/agent/governance.py` — `AgentAuthority`
Per-agent **charters** (which tools each agent may call), **budgets** (token/step caps), and the **audit sink** — every allow/deny is written to `audit_log`. Also injection markers for prompt-injection defense.
- *Likely Q:* "What if an agent tries a tool outside its charter?" → Authority denies and audits it; the turn degrades gracefully.

## 3.4 `backend/agent/pipelines.py` — deterministic tool sequences
Each agent's fixed pipeline (Diagnostic: retrieve_rag→match_history; Reliability: check_equipment_health→estimate_rul; Supervisor: score_priority; Planner: check_spares→procurement_rule; Analyst: query_records).
- *Likely Q:* "Why fixed order?" → reproducibility + auditability (see Part 2 Q2).

## 3.5 `backend/agent/synthesis.py` — the SLM
`OllamaSynthesizer` (or hosted Groq/OpenAI via the `openai` client). Does **classify**, **synthesize card**, and **one-shot repair** with `format="json"` + the card schema, temperature ~0.1. Reads provider token usage (Groq/OpenAI `usage`; Ollama `eval_count`/`prompt_eval_count`) for the monitor.
- *Likely Q:* "Local vs hosted?" → `SYNTHESIS_BACKEND` switches; on-prem Ollama for data sovereignty, Groq for the GPU-less cloud demo; `/healthz` reports the active model.

## 3.6 `backend/agent/persistence.py` — egress
`_ensure_session` (creates the session row + logs the user message — fixed an FK bug that silently dropped history), `write_turn` (assistant + agent_event rows), `commit_action` (HITL-approved COMMIT). Best-effort: persistence never crashes a turn.

## 3.7 `backend/tools/*`
- `rag.py` — hybrid retrieval (pgvector + full-text), prod fallback.
- `ml_tools.py` — loads the 5 published models once (`@lru_cache`); `check_equipment_health`, `estimate_rul`, `analyze_defect`, `predict_failure`, `predict_pdm_24h`, `model_scorecard` (live held-out inference — every advertised number is real).
- `text_to_sql.py` — **governed, SELECT-only** NL→SQL over curated analytic views (the Analyst agent). Injection-safe.
- `plant_summary.py` — deterministic plant KPI computation (availability, downtime-at-risk ₹).

## 3.8 `backend/db/*`
`migrations.sql` (idempotent schema: enums, equipment, sensors, doc_chunks `vector(768)` + HNSW, chat tables, audit_log, llm_usage/llm_cache, RLS), `connection.py` (pooled psycopg, refuses empty `DATABASE_URL`), `apply_migrations.py` (runner + seeds).

## 3.9 `ml/*` — classical models (train→publish→serve parity)
Five models: anomaly (IsolationForest+EWMA), RUL (XGBoost on C-MAPSS), failure (XGBoost on AI4I), defect (LightGBM on UCI Steel Plates), Azure PdM (XGBoost 24h-ahead). `shared/feature_config.json` is the **train/serve parity contract** read by both `train.py` and `ml_tools.py`. Artifacts published to `backend/models/`.
- *Likely Q:* "How do you prevent train/serve skew?" → shared feature config + deterministic (`random_state=42`) + a live scorecard that re-runs inference on committed held-out rows.

## 3.10 `finetune/*` & `data/*`
`finetune/` — SFT generation from real tools, quality gates, QLoRA runner, GGUF export, eval/promotion. `data/` — `fetch_data.py` (public benchmarks), `synthetic/generate_sensors.py` (physics-shaped 30-day stream — honestly a simulation), `corpus/seed_corpus.py` (PDF→chunks→`corpus_ingest.sql`).

## 3.11 Frontend
`lib/api.ts` (typed fetch wrappers + bearer auth), `AuthProvider` (role from JWT), `CopilotWidget` (global fixed-height copilot + history), admin page (live metrics + token monitor), `Cards.tsx` (renders typed cards), `PlantTwin3D` (react-three-fiber).

---

# Part 4 — Round 1 ML Deep Dive (Defect Detection)

**Problem:** binary **steel-coil defect** classification, 49 process features across 5 stages (X1–X49), **severe imbalance (~1:40)**, missing values, heavy skew. Metric prioritizes **catching every defect** (recall).

### Q. Walk me through your Round-1 solution.
**A.** Pipeline in [`defect_detection.py`](../Tata_Steel_Round1_Solution/defect_detection.py):
1. **Audit & EDA** — class distribution, missing-value map, skew, per-class mean differences.
2. **Preprocessing** — **median imputation** (robust to outliers), **1st–99th percentile clipping** per feature, **mutual-information** feature ranking.
3. **Feature engineering** (`engineer_features`) — aggregate stats (mean/std/range/IQR/skew/kurtosis), **stage-wise** means/std/max (X1–10 … X41–49), **cross-stage diffs & ratios**, **spike/crash counts** (>2σ), and an **IsolationForest anomaly score** fit on normal coils only (no leakage).
4. **Model** — **5-fold StratifiedKFold ensemble** of **LightGBM + XGBoost + CatBoost**, each with class weighting (`class_weight={0:1,1:40}` / `scale_pos_weight=40`); OOF + averaged test probabilities.
5. **Threshold optimization** — sweep thresholds on OOF, pick the one giving **Recall = 1.0 (zero false negatives)** with **max precision**. This is the key decision.
6. **Submission** — apply threshold, validate shape/columns/values, write CSV.

### Q. Why optimize for Recall = 1.0 instead of accuracy or F1?
**A.** A **missed defect** (false negative) ships a bad coil to a customer — far costlier than a false alarm that triggers a quick re-inspection. With 1:40 imbalance, accuracy is a trap (predict "all normal" → 97.6% accuracy, 0 defects caught). So I tune the **decision threshold** to guarantee recall, then maximize precision to keep false alarms manageable. This is exactly the cost-asymmetry framing maintenance leaders care about.

### Q. How did you handle the imbalance?
**A.** Three levers: **class weights** (1:40) inside each booster, **threshold tuning** (the biggest lever — default 0.5 is wrong for imbalance), and I evaluated **SMOTE/BorderlineSMOTE/SMOTETomek** as resampling options. I kept the trees + class-weights + threshold combo because it avoided synthetic-sample artifacts while hitting recall=1.0.

### Q. Why an ensemble of three gradient boosters?
**A.** LightGBM (leaf-wise, fast), XGBoost (level-wise, regularized), CatBoost (ordered boosting, robust defaults) make **decorrelated errors**; averaging their probabilities reduces variance and is steadier across folds than any single model. StratifiedKFold preserves the rare-class ratio in every fold; OOF predictions give an unbiased threshold-tuning set.

### Q. Leakage safety?
**A.** Imputer/clip/IsolationForest are **fit on training only** (the iso-forest on *normal* training coils) and applied to test; threshold is chosen on **out-of-fold** predictions, never on test. The stage structure was domain knowledge, not target-derived.

> This directly proves the JD's "classification & regression problems," "feature engineering," and "data pipelines."

---

# Part 5 — Live-Coding / Whiteboard Prep

> Keep solutions short and explain trade-offs while coding.

### 5.1 Python — find top-K by mutual-info-like score / general fluency
```python
# Generator + decorator fluency (commonly probed)
from functools import lru_cache
import time

def timed(fn):
    def wrap(*a, **k):
        t = time.perf_counter(); r = fn(*a, **k)
        print(f"{fn.__name__}: {time.perf_counter()-t:.4f}s"); return r
    return wrap

@lru_cache(maxsize=None)
def fib(n): return n if n < 2 else fib(n-1) + fib(n-2)   # memoized O(n)
```
Talk: list vs generator (memory), `lru_cache` (the same idea as my LLM cache), big-O.

### 5.2 SQL / PostgreSQL — window function (used in the app's analytics)
```sql
-- Per-equipment downtime ranking (window function)
SELECT equipment_id,
       SUM(downtime_hrs) AS total_downtime,
       RANK() OVER (ORDER BY SUM(downtime_hrs) DESC) AS rnk
FROM breakdown_history
GROUP BY equipment_id
ORDER BY total_downtime DESC;
```
```sql
-- pgvector nearest-neighbour retrieval (the heart of RAG)
SELECT id, content, 1 - (embedding <=> :q) AS score   -- <=> = cosine distance
FROM doc_chunks
ORDER BY embedding <=> :q
LIMIT 5;
```
Talk: `<=>` cosine vs `<->` L2; **HNSW** index for ANN; `tsvector`/GIN for full-text; why **hybrid** beats either alone; SQL vs NoSQL (when you'd reach for a document/KV store).

### 5.3 ML — metrics & threshold (Round-1 muscle)
```python
import numpy as np
from sklearn.metrics import recall_score, precision_score

def best_threshold_for_full_recall(y, proba):
    ts = np.arange(0.001, 0.6, 0.001)
    best_t, best_p = 0.5, -1
    for t in ts:
        pred = (proba >= t).astype(int)
        if recall_score(y, pred, zero_division=0) == 1.0:
            p = precision_score(y, pred, zero_division=0)
            if p > best_p: best_p, best_t = p, t
    return best_t, best_p
```

### 5.4 Deep learning — tiny PyTorch LSTM (JD names CNN/RNN/LSTM)
```python
import torch, torch.nn as nn

class RULModel(nn.Module):                 # sensor window -> remaining useful life
    def __init__(self, n_features, hidden=64):
        super().__init__()
        self.lstm = nn.LSTM(n_features, hidden, batch_first=True)
        self.head = nn.Linear(hidden, 1)
    def forward(self, x):                  # x: (batch, seq_len, n_features)
        out, (h, _) = self.lstm(x)
        return self.head(h[-1]).squeeze(-1)
```
Talk: LSTM gates solve vanishing gradients for long sequences; CNN for spatial (defect images); when you'd pick GBMs over DL (tabular, small data — like Round 1).

### 5.5 Agentic — minimal LangGraph graph + tool + structured output
```python
from langgraph.graph import StateGraph, END
from pydantic import BaseModel
from typing import TypedDict

class Card(BaseModel):           # prompt-to-template: LLM fills THIS
    fault: str; confidence: str; citation_refs: list[str]

class S(TypedDict):
    query: str; evidence: list[str]; card: dict

def retrieve(s):  return {"evidence": rag_search(s["query"])}      # tool
def synthesize(s): return {"card": llm_json(s["query"], s["evidence"], schema=Card)}
def guard(s):                                                     # cite-or-refuse
    refs = s["card"].get("citation_refs", [])
    return "ok" if all(r in s["evidence"] for r in refs) else "degrade"

g = StateGraph(S)
g.add_node("retrieve", retrieve); g.add_node("synthesize", synthesize)
g.set_entry_point("retrieve"); g.add_edge("retrieve", "synthesize")
g.add_conditional_edges("synthesize", guard, {"ok": END, "degrade": END})
app = g.compile()
```
Talk: this *is* ForgeSight in miniature — state, nodes=steps, conditional edges=guardrails, checkpointer=memory.

### 5.6 Minimal RAG loop
```python
def rag_answer(q, chunks, embed, llm):
    qv = embed(q)
    ranked = sorted(chunks, key=lambda c: cosine(qv, c.vec), reverse=True)[:5]
    ctx = "\n".join(f"[{c.ref}] {c.text}" for c in ranked)
    return llm(f"Answer using ONLY this context, cite [ref]:\n{ctx}\n\nQ: {q}")
```

---

# Part 6 — Fundamentals Q&A (mapped to AI_Engineering_Notes/)

> Each cluster cites the matching reference PDF in `AI_Engineering_Notes/`.

## 6.1 Classical ML — *`100 Machine Learning Interview Questions and Answers.pdf`, `ML-1.pdf`, `Hyperparameters.pdf`*
- **Bias–variance:** underfit (high bias) vs overfit (high variance); control via regularization, more data, simpler/complex models, CV.
- **Regularization:** L1 (Lasso, sparsity/feature selection) vs L2 (Ridge, shrinkage); dropout/early-stopping in DL.
- **Imbalance:** class weights, resampling (SMOTE), **threshold tuning**, and **PR-AUC/recall over accuracy** (Round 1).
- **Time-series:** stationarity, lag/rolling features, **no shuffling** in CV (use time-based splits), leakage from future.
- **Optimization:** gradient descent variants (SGD/Adam), learning-rate schedules; combinatorial optimization for spares.

## 6.2 Deep learning — *`Deep_Learning_Interview_Questions_Answers.pdf`, `VIP Cheatsheet - Transformers & LLMs.pdf`*
- **CNN** (weight sharing, local receptive fields — images/defect maps), **RNN/LSTM/GRU** (sequences; gates fix vanishing gradients), **Transformer/attention** (parallel, long-range; Q·Kᵀ/√d softmax · V).
- **Backprop**, vanishing/exploding gradients (ReLU, residuals, norm, clipping), batch/layer norm.

## 6.3 GenAI / LLM — *`LLM Fundamentals.pdf`, `Large Language Models (LLMs) Cheat Sheet.pdf`, `GenAI_Interview_Questions.pdf`, `Top_9_LLM API_PARAMETERS.pdf`*
- **Tokens/context window**; **temperature/top_p/top_k** (I use temp ~0.1 + `format=json` for deterministic cards); greedy vs sampling.
- **Hallucination** mitigation: RAG grounding, constrained decoding, cite-or-refuse, low temperature.
- **RAG vs fine-tune vs prompt** (Part 2 Q4); **SLM vs LLM** (cost/latency/privacy vs raw capability — I chose a 3B SLM for on-prem).
- **Quantization** (Q4_K_M GGUF — 4-bit, fits commodity GPU/CPU), **LoRA/QLoRA** (*`Master LLM Fine-tuning.pdf`, `A HANDS-ON GUIDE TO FINE TUNING LLM...pdf`*): freeze base, train low-rank adapters; QLoRA adds 4-bit base + paged optimizers.
- **Chunking strategies** (*RAG notes*): fixed, recursive, semantic, **structure-aware** (mine), parent-child; trade-offs in retrieval precision vs context.
- **Semantic caching** (*`Asynchronous Verified Semantic Caching for Tiered LLM Architectures.pdf`*): embed query, reuse near-duplicate answers — my `semantic_cache`/`llm_cache`.
- **Prompt engineering** (*`Prompt Engineering Interview Questions.pdf`*): few-shot, role/system prompts, **prompt-to-template** (force structured output), guardrails.

## 6.4 Agentic & LangGraph — *`Agentic Design Patterns with LangGraph.pdf`, `Building Enterprise-Grade Agent Systems with Langraph.pdf`, `Langgraph interview questions.pdf`, `Agentic_AI_Interview_Q&A.pdf`*
- **Agent patterns:** reflection, tool-use, planning, multi-agent (supervisor/worker — mine is supervisor + chartered specialists).
- **LangGraph vs LangChain:** graphs = explicit stateful control flow + checkpointing + conditional edges (governance); chains = linear. **Google ADK** = Google's agent dev kit (same concepts; be ready to say you'd adopt the org standard).
- **Why governed > autonomous** for plants (Part 2 Q2).

## 6.5 MLOps — *`AIOPS & MLOPS.pdf`, `AI_Engineering_Guidebook.pdf`*
- Model registry/versioning, **train/serve parity** (my feature_config), CI/CD, **monitoring & drift** (data/concept drift), canary/rollback, cost/latency telemetry (my token monitor), reproducibility (seeds, pinned deps).

## 6.6 Databases & cloud — *`PostgreSQLNotesForProfessionals.pdf`*
- **SQL vs NoSQL** (ACID/relational vs schema-flexible/scale); **PostgreSQL** indexes (B-tree/GIN/HNSW), JSONB, window functions; **pgvector** for embeddings. **Serverless** (Cloud Run/Lambda/Functions) vs **K8s/GKE** (long-running/GPU); pick by workload.

## 6.7 Responsible AI
Bias mitigation (balanced metrics, feedback correction), privacy (on-prem SLM, RLS, secret hygiene), explainability (citations, audit), human-in-the-loop.

---

# Part 7 — Behavioral & Leadership (STAR)

> The role is **Manager/Area Manager** — they're checking leadership + communication, not just code.

- **Ownership / end-to-end delivery (S-T-A-R):** *S:* fragmented maintenance decisions cause downtime. *T:* build a trustworthy AI copilot in a hackathon timeline. *A:* designed the governed multi-agent architecture, built RAG + 5 ML models + SLM synthesis + the full-stack app, deployed to Railway/Vercel/Supabase, added an admin cost monitor. *R:* a working, cited, audited system that diagnoses in ~90s; Top 40 of the hackathon.
- **Cost-aware decision (recall=1.0):** framed defect detection around the **business cost of a missed defect**, not accuracy — exactly how I'd justify model choices to plant leadership.
- **Handling constraints / trade-offs:** no cloud GPU → built a **hosted-fallback** so the demo works while keeping the on-prem SLM as the real design; honest about what's simulated.
- **Communicating to non-technical stakeholders:** the **Leadership ROI view** translates model output into ₹ savings and confidence — speaking the language of operations/management.
- **Managing multiple workstreams:** ML models, RAG corpus, agent governance, frontend, deployment — sequenced with clear "passes"/milestones and verification at each.
- **Industry-5.0 vision for Tata Steel:** agents augment (not replace) engineers — "agents propose, humans commit"; on-prem SLMs for data sovereignty; scale the pattern from maintenance to quality, energy, and supply-chain copilots across plants.

---

# Part 8 — Rapid-Fire, Curveballs & Honest Limitations

**Pre-empt these honestly (builds credibility):**
- *"Is the sensor data real?"* — The stream is a **physics-shaped simulation** (no public real-time steel feed); the governance, ML inference, RAG over **real OEM manuals**, and reasoning on top are real. On a real plant I'd wire the historian/OPC-UA.
- *"Are the ML models plant-specific?"* — They validate the **method** on public benchmarks (C-MAPSS, AI4I, UCI Steel Plates, Azure PdM); on real data I'd retrain per asset. The anomaly model runs live on the (simulated) plant sensors.
- *"Cloud demo vs on-prem?"* — Cloud demo uses Groq (no GPU) + full-text-primary retrieval; on-prem uses the fine-tuned Qwen via Ollama + hybrid retrieval. `/healthz` shows the active backend.
- *"Why 3B, not GPT-4?"* — cost, latency, and **privacy** — and constrained decoding + tools make a small model reliable enough for the structured task.

**Rapid-fire likely:**
- *Precision vs recall?* trade-off; pick by cost asymmetry. *PR-AUC vs ROC-AUC?* PR for imbalance. *Overfitting fixes?* regularize/CV/more data/simpler model. *Vanishing gradient?* ReLU/residual/norm/LSTM gates. *Vector vs keyword search?* semantic vs lexical → hybrid. *Idempotent migrations?* `IF NOT EXISTS`/`ON CONFLICT`. *Stateless API why?* horizontal scale. *Temperature 0?* determinism. *LoRA rank?* capacity vs params.

**Closing line:** *"ForgeSight is my proof that agentic AI can be trustworthy enough for heavy industry — cited, audited, human-gated, and able to run on-prem. I'd love to scale that pattern across Tata Steel's value chain."*

---

### One-page cheat sheet (glance before the call)
- **Pitch:** governed multi-agent maintenance copilot → fault code to **auditable, cited fix plan in ~90s**.
- **Trust:** tools compute, LLM narrates; **cite-or-refuse**; HITL for COMMITs; full audit log; on-prem SLM.
- **Flow:** ingest_and_authorize → cache_lookup → classify_intent → agent pipeline (RAG/ML/SQL) → synthesize → guardrail_validate → respond/human_gate/repair/degrade.
- **Stack:** FastAPI + LangGraph · Postgres + pgvector · Qwen-3B (Ollama/Groq, QLoRA) · Next.js · Railway/Vercel/Supabase.
- **Round 1:** 1:40 imbalance · stage/spike/iso features · LGBM+XGB+CatBoost 5-fold · **threshold→Recall=1.0**.
- **JD hooks:** Agentic · RAG+chunking · prompt-to-template · SLM/fine-tune · PostgreSQL · MLOps · IT-OT · responsible AI.
