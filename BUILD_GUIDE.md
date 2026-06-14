# ForgeSight — BUILD GUIDE for an AI Coding Agent
### Intelligent Maintenance Wizard · Tata Steel AI Hackathon 2026
**Audience:** an autonomous coding agent (Copilot agent mode / similar). **Goal:** build the system described in `forgesight-v3-final.md` end-to-end. This file is the executable build order. Read `forgesight-v3-final.md`, `agent_governance.py`, `seed_corpus.py`, `rag_retrieval.py`, and `sft-dataset-spec.md` as the authoritative design; this file tells you *how to build it, in what order, and how to verify each step*.

---

## 0. HOW TO USE THIS DOCUMENT (agent rules)

1. **Build in the phase order below. Do not skip ahead.** Each phase ends with a **VERIFICATION GATE** — a concrete, runnable check. Do not start the next phase until the gate passes. If a gate fails, fix it before continuing.
2. **Tools follow the TEST → CONFIGURE → INTEGRATE loop, in that order.** For every external tool (Supabase, Ollama, CopilotKit, LangGraph, Langfuse): first write a tiny standalone script that proves the tool works in isolation (TEST), then wire its config/env (CONFIGURE), then connect it to the app (INTEGRATE). Never integrate a tool you have not first tested in isolation.
3. **Dataset first, always.** Nothing in ML or the agent is built until Phase 1 datasets exist and validate. The corpus and sensor data are the foundation every downstream component consumes.
4. **ML and fine-tuning live in their OWN directories as notebooks**, each with a `dataset/` subdirectory, each producing versioned artifacts that are then copied into the backend's `/models`. Training code never runs inside the API.
5. **Schema-first.** Freeze Pydantic models (backend) and their TypeScript mirrors (frontend) before building features that depend on them. One schema, mirrored — never two hand-maintained copies.
6. **Stick to the PS.** Section 11 is the requirement checklist. Every feature maps to a PS clause. Innovation is allowed only where Section 9 marks it — do not invent scope that risks the core scenarios.
7. **Keep the demo runnable offline.** SLM-first; no runtime cloud-LLM dependency; cached fallback behind `DEMO_MODE`.
8. **Commit after every passing gate** with a message naming the gate.

---

## 1. REPOSITORY FILE STRUCTURE

Create exactly this structure. Notebook directories (`ml/`, `finetune/`) are self-contained with their own `dataset/` subdirs and produce artifacts consumed by `backend/models/`.

```
forgesight/
├── README.md                      # install, demo credentials, run order, architecture summary
├── docker-compose.yml             # backend + (optional) local services for submission repro
├── .env.example                   # every env var, documented, no secrets
│
├── data/                          # ← PHASE 1: shared raw + generated data (the foundation)
│   ├── fetch_data.py              # downloads all public datasets (URLs in §2) — idempotent
│   ├── raw/                       # downloaded benchmarks (gitignored; fetch_data repopulates)
│   │   ├── cmapss/                # NASA C-MAPSS FD001
│   │   ├── ai4i/                  # AI4I 2020
│   │   ├── cwru/                  # CWRU bearing
│   │   ├── ims/                   # NASA IMS bearing (degradation shape template)
│   │   ├── steel_plates/          # UCI Steel Plates Faults
│   │   └── azure_pdm/             # optional schema template
│   ├── synthetic/                 # ← generated steel layer
│   │   ├── generate_sensors.py    # 6 equipment × 30d streams + injected degradation + is_anomaly labels
│   │   ├── sensor_readings.csv
│   │   ├── breakdown_history.json # from seed_corpus.py
│   │   └── manuals/               # real OEM PDFs you place here (ABB/SKF/fan)
│   └── corpus/
│       ├── seed_corpus.py         # (provided) chunk + embed + emit corpus_ingest.sql
│       └── corpus_ingest.sql      # generated
│
├── ml/                            # ← PHASE 2: classical ML — SEPARATE notebook dir per model
│   ├── anomaly/
│   │   ├── dataset/               # symlink/copy of relevant synthetic + (val) labels
│   │   ├── 01_explore.ipynb
│   │   ├── 02_train_isolation_forest.ipynb
│   │   ├── 03_evaluate.ipynb      # precision/recall + DETECTION LEAD TIME
│   │   └── export/                # anomaly_iforest_v1.joblib, scaler_v1.joblib
│   ├── failure_classifier/
│   │   ├── dataset/               # AI4I 2020
│   │   ├── 01_explore.ipynb
│   │   ├── 02_train_xgboost.ipynb # scale_pos_weight, stratified, drop RNF + leakage cols
│   │   ├── 03_evaluate.ipynb      # failure-class F1/recall + SHAP
│   │   └── export/                # failure_xgb_v1.json
│   ├── rul/
│   │   ├── dataset/               # C-MAPSS FD001
│   │   ├── 01_explore.ipynb
│   │   ├── 02_train_rul.ipynb     # piecewise RUL cap=125, SPLIT BY UNIT, windowed features
│   │   ├── 03_evaluate.ipynb      # RMSE (by unit)
│   │   └── export/                # rul_xgb_v1.joblib
│   ├── defect/
│   │   ├── dataset/               # UCI Steel Plates Faults
│   │   ├── 01_explore.ipynb
│   │   ├── 02_train_lightgbm.ipynb# PCA-residual + kNN-dist features, LEAKAGE-SAFE per-fold
│   │   ├── 03_evaluate.ipynb      # PR-AUC, OOF threshold (precision-first → F-beta3)
│   │   └── export/                # defect_pipeline_v1.joblib, threshold.json
│   ├── bearing_features/          # CWRU → RMS/kurtosis/crest (feeds anomaly narrative)
│   │   └── 01_extract_features.ipynb
│   ├── shared/
│   │   ├── feature_config.json    # window sizes, column order, scaling — READ BY TRAIN + SERVE
│   │   └── metrics.json           # aggregated CV/test metrics → "About the models" UI panel
│   └── README.md                  # how to run notebooks, export artifacts to backend/models
│
├── finetune/                      # ← PHASE 3: SLM fine-tune — SEPARATE notebook dir
│   ├── dataset/
│   │   ├── prompt_builder.py      # SHARED with backend (train/serve parity) — context block serializer
│   │   ├── generate_sft.py        # builds ~2,150 pairs (see sft-dataset-spec.md) from real tool outputs
│   │   ├── sft_train.jsonl
│   │   ├── sft_eval.jsonl
│   │   └── quality_gates.py       # JSON valid · citation-subset · number-fidelity · LOTO-first
│   ├── 01_generate_dataset.ipynb
│   ├── 02_unsloth_qlora.ipynb     # Colab T4; r=16, 2-3 epochs; export GGUF + merged
│   ├── 03_evaluate_vs_base.ipynb  # base-vs-FT table (FR-1 merit evidence)
│   └── export/                    # qwen2.5-3b-forgesight.gguf (→ Ollama Modelfile)
│
├── backend/                       # ← PHASE 4-6: FastAPI + governed agent
│   ├── pyproject.toml             # incl. [tool.vercel] only if edge routes used (see deploy)
│   ├── requirements.txt
│   ├── server.py                  # FastAPI app instance `app` + lifespan (load models, connect DB)
│   ├── config.py                  # pydantic-settings; MODEL_BACKEND=slm_only|hybrid; DEMO_MODE
│   ├── auth/
│   │   ├── jwt_dep.py             # current_user / require_role (Supabase JWT verify)
│   │   └── audit.py               # audit_log writer (used by AgentAuthority)
│   ├── agent/
│   │   ├── governance.py          # (provided agent_governance.py) state/authority/guardrails/controller
│   │   ├── charters.py            # AGENT_CHARTERS incl. pipeline tuples
│   │   ├── pipelines.py           # deterministic per-agent tool sequences (NOT ReAct loops)
│   │   ├── synthesis.py           # SLM card synthesis (Ollama format=schema) + repair
│   │   └── prompt_builder.py      # imported from finetune/dataset (symlink) — parity
│   ├── tools/
│   │   ├── rag.py                 # (provided rag_retrieval.py) hybrid + metadata filter
│   │   ├── ml_tools.py            # check_equipment_health / estimate_rul / analyze_defect
│   │   ├── deterministic.py       # score_priority matrix · procurement_rule · severity rules
│   │   ├── spares.py              # check_spares (SQL)
│   │   ├── reports.py             # ReportLab PDF
│   │   └── analytics.py           # ⭐ governed text-to-SQL (read-only views, SqlCard) — Phase 7
│   ├── schemas/
│   │   └── cards.py               # Pydantic: Diagnosis, ChecklistCard, RULEstimate, ... (schema-first)
│   ├── models/                    # ← artifacts COPIED from ml/*/export + finetune/export Modelfile
│   ├── scheduler/
│   │   └── health_scan.py         # APScheduler 30s job → equipment_health + alerts
│   ├── db/
│   │   ├── migrations.sql         # full schema + RLS + read-only analytics views + SELECT-only role
│   │   └── seed_accounts.sql      # engineer@demo / admin@demo (pre-confirmed)
│   └── copilotkit_endpoint.py     # CoAgents bridge (threadId persistence)
│
├── frontend/                      # ← PHASE 5: Next.js 15
│   ├── package.json
│   ├── middleware.ts              # auth route protection + /simulate,/admin admin-gate
│   ├── app/
│   │   ├── login/  overview/  priority/  equipment/[id]/  reports/  admin/  simulate/
│   ├── components/
│   │   ├── atoms/                 # StatusBadge RiskPill RulCountdown EvidenceChip SparesChip
│   │   │                          # AgentByline SessionRow ApprovalPrompt SqlCard
│   │   ├── cards/                 # DiagnosisCard ChecklistCard RiskCard WaitAssessmentCard ...
│   │   ├── copilot/               # sidebar, session history, delegation stream, HITL prompts
│   │   └── charts/                # SensorTrend (anomaly markers + threshold lines)
│   ├── lib/
│   │   ├── schemas.ts             # TS mirror of backend/schemas/cards.py
│   │   └── supabase.ts            # client + Realtime subscriptions
│   └── styles/tokens.css          # design system tokens (§ UI)
│
└── docs/                          # ← submission deliverables (§9)
    ├── architecture.md            # = forgesight-v3-final.md
    ├── sample_io.md               # golden inputs + outputs per scenario
    └── demo_script.md             # the 5:30 choreography
```

---

## 2. PHASE 1 — DATASETS FIRST (the foundation — build nothing else until this gate passes)

**TEST → CONFIGURE → INTEGRATE applies to data too: download → validate shape → make available to notebooks.**

### 2.1 `data/fetch_data.py` — download all benchmarks (idempotent)
Download into `data/raw/`. Reference URLs (use these exact sources):
- **NASA C-MAPSS FD001 (RUL):** zip https://phm-datasets.s3.amazonaws.com/NASA/6.+Turbofan+Engine+Degradation+Simulation+Data+Set.zip · repo https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/ · Kaggle mirror https://www.kaggle.com/datasets/bishals098/nasa-turbofan-engine-degradation-simulation
- **AI4I 2020 (failure classification):** `from ucimlrepo import fetch_ucirepo; fetch_ucirepo(id=601)` (https://pypi.org/project/ucimlrepo/) · UCI https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset · Kaggle https://www.kaggle.com/datasets/stephanmatzka/predictive-maintenance-dataset-ai4i-2020
- **CWRU bearing (vibration):** https://engineering.case.edu/bearingdatacenter · Kaggle https://www.kaggle.com/datasets/brjapon/cwru-bearing-datasets
- **NASA IMS bearing (degradation-shape template):** PCoE page above · Kaggle https://www.kaggle.com/datasets/vinayak123tyagi/bearing-dataset
- **UCI Steel Plates Faults (steel-domain defect):** `fetch_ucirepo(id=198)` · https://archive.ics.uci.edu/dataset/198/steel+plates+faults
- **Microsoft Azure PdM (optional schema template):** https://www.kaggle.com/datasets/arnabbiswas1/microsoft-azure-predictive-maintenance

For Kaggle sources, support both a Kaggle-API path (if `KAGGLE_USERNAME`/`KAGGLE_KEY` set) and a manual-placement fallback (print instructions, check for the file). Never fail silently.

### 2.2 `data/synthetic/generate_sensors.py` — the steel layer
6 equipment (ids from `seed_corpus.py` EQUIPMENT). For each: 30 days × 1 reading/5 min ≈ 8,640 rows × {vibration_de, vibration_nde, bearing_temp, motor_current, rpm, load_pct}. Healthy baseline = daily-cycle + noise. Inject: (a) Sinter ID Fan #2 — gradual bearing-vibration ramp whose *shape* is borrowed from a NASA IMS run-to-failure trajectory, crossing 7.1 mm/s near day 30; (b) F3 stand — a discrete VFD trip event. Emit `sensor_readings.csv` and a separate `is_anomaly` label column for the injected windows (evaluation only). Align fault codes/dates with `breakdown_history.json` (BR-2024-0312 etc.).

### 2.3 `data/corpus/seed_corpus.py` (provided) — run it
Place 2–3 real OEM PDFs in `data/synthetic/manuals/`, then run → `corpus_ingest.sql`. Set `FIRECRAWL_API_KEY` only if scraping HTML knowledge pages (dev-time).

### ✅ VERIFICATION GATE 1 (datasets)
- `python data/fetch_data.py` → all six `raw/` subdirs populated; print row counts: C-MAPSS train_FD001 = 20,631 rows; AI4I = 10,000 rows; Steel Plates = 1,941 rows.
- `python data/synthetic/generate_sensors.py` → `sensor_readings.csv` ≈ 52k rows, 6 equipment, `is_anomaly` present, fan ramp visibly crosses threshold (assert max vibration_de on sinter-fan-2 > 7.1).
- `python data/corpus/seed_corpus.py` → `corpus_ingest.sql` non-empty; print chunk counts by doc_type (manual/sop/report all > 0).
**Do not proceed to Phase 2 until all three print correct shapes.**

---

## 3. PHASE 2 — CLASSICAL ML (separate notebook dir per model · dataset/ subdir · export artifacts)

**Rule:** each model directory is self-contained. Its `dataset/` holds (or symlinks) only what it needs. Each `02_train*` notebook ENDS by writing a versioned artifact into its `export/`. A final cell in each `03_evaluate` notebook appends its metrics to `ml/shared/metrics.json`. After all four pass, copy artifacts to `backend/models/`.

### 3.1 `ml/anomaly/` — IsolationForest + control limits
- 02: fit on first 20 days (healthy) of `sensor_readings.csv`; standardize (save scaler); `IsolationForest(contamination='auto', random_state=42)`. Also compute per-sensor EWMA control limits.
- 03: evaluate on last 10 days using `is_anomaly`; report precision, recall, and **detection lead time** (days between first true-positive flag and threshold crossing). Export `anomaly_iforest_v1.joblib`, `scaler_v1.joblib`.

### 3.2 `ml/failure_classifier/` — XGBoost on AI4I 2020
- 02: drop `UDI`, `Product ID` (leakage), drop `RNF` from the multiclass target (document why). Stratified 80/20; `scale_pos_weight` for imbalance. 
- 03: report **failure-class recall & F1 and PR-AUC** (never accuracy — 3.4% positive). SHAP summary → top features. Export `failure_xgb_v1.json`.

### 3.3 `ml/rul/` — XGBoost on C-MAPSS FD001
- 02: derive `RUL = max_cycle − cycle`, **cap at 125** (piecewise linear). Drop near-constant sensors; rolling mean/std (window 5–10) on the rest. **Split by engine unit (GroupShuffleSplit), never by row.**
- 03: RMSE on held-out units (target ~16–18). Export `rul_xgb_v1.joblib`.

### 3.4 `ml/defect/` — LightGBM leakage-safe pipeline on UCI Steel Plates
- 02: build the pipeline from `sft-dataset-spec` review and earlier design — median-impute + `*_isna` flags; descriptive + gradient + rolling-volatility features; **PCA-reconstruction-residual and kNN-distance-to-normal fit INSIDE each CV fold** (sklearn `Pipeline` + custom transformers, refit per fold — NO global fit, that's the leakage bug). LightGBM with `scale_pos_weight`.
- 03: RepeatedStratifiedKFold (5×2); **OOF-only threshold** (highest-precision reaching target recall, else max F-beta=3). PR-AUC headline. SHAP top contributors. Export `defect_pipeline_v1.joblib` (full Pipeline) + `threshold.json` (cutoff + OOF metrics + fold spread).

### 3.5 `ml/bearing_features/` — CWRU
Extract RMS/kurtosis/crest-factor per window from 12 kHz drive-end signals; document as the feature basis for vibration health (supports the sinter-fan narrative). Optional small classifier.

### 3.6 `ml/shared/feature_config.json`
Single source of truth for window sizes, column order, scaling params — imported by BOTH notebooks and `backend/tools/ml_tools.py`. This guarantees train/serve feature parity.

### ✅ VERIFICATION GATE 2 (ML)
- All four `export/` dirs contain artifacts; `ml/shared/metrics.json` lists a metric per model.
- Sanity: load each artifact in a fresh process and run one prediction — no error, output in expected range.
- Copy artifacts → `backend/models/`. Assert `feature_config.json` is identical in `ml/shared/` and referenced by backend.
**Do not build `ml_tools.py` until artifacts load cleanly in a fresh process.**

---

## 4. PHASE 3 — SLM FINE-TUNE (separate notebook dir · dataset/ subdir · GGUF export)

### 4.1 `finetune/dataset/prompt_builder.py` — the parity module (build FIRST)
The context-block serializer (equipment header · tool_results JSON · numbered citations · history summary), static-first ordering. **This exact file is symlinked into `backend/agent/prompt_builder.py`** so training and runtime inputs are byte-identical. This is the single most important correctness decision in the fine-tune — build and freeze it before generating data.

### 4.2 `01_generate_dataset.ipynb`
Per `sft-dataset-spec.md`: ~2,150 pairs across 10 tasks (intent, all card types, repair, no-evidence refusal). Generate by running the REAL tools (Phase 1 corpus + Phase 2 artifacts) to get genuine tool_results + citations, then a hosted model (dev-time) writes the target card obeying the schema. Run `quality_gates.py` (100% automated: JSON valid · citation-subset · number-fidelity · LOTO-first) + flag 50 for manual review.

### 4.3 `02_unsloth_qlora.ipynb` (Colab T4)
Unsloth QLoRA on Qwen2.5-3B-Instruct (try 7B if VRAM allows): r=16, alpha=16, lr 2e-4, 2–3 epochs, max_seq 4096, packing on. Export BOTH `save_pretrained_gguf` (Q4_K_M → Ollama) and `save_pretrained_merged` (→ ⭐ vLLM). Links: Unsloth https://github.com/unslothai/unsloth · Qwen https://huggingface.co/Qwen/Qwen2.5-3B-Instruct

### 4.4 `03_evaluate_vs_base.ipynb`
Eval split + DeepEval: intent accuracy, JSON-validity, citation-subset compliance, number-fidelity; base-vs-fine-tuned table. **Promotion rule:** ship the fine-tune only if it beats base on citation compliance AND number fidelity; else ship base + few-shot, present FT as in-progress.

### 4.5 Integrate into Ollama
Write a `Modelfile` (FROM the GGUF) → `ollama create qwen-forgesight`. The backend points `MODEL_BACKEND=slm_only` at this model with `format=<card schema>` constrained decoding.

### ✅ VERIFICATION GATE 3 (fine-tune)
- `ollama run qwen-forgesight` answers a sample diagnosis prompt with valid card JSON (constrained).
- base-vs-FT table exists in `finetune/03`. Promotion decision recorded.
**This gate can run in parallel with Phase 4–5 (it's on Colab); don't block backend work waiting on it — base Qwen is the fallback.**

---

## 5. PHASE 4 — BACKEND (TEST → CONFIGURE → INTEGRATE per tool)

### 5.1 Supabase (DB + auth)
- **TEST:** standalone script connects, runs `SELECT 1`, creates one row, reads it back.
- **CONFIGURE:** run `db/migrations.sql` (full schema + RLS + read-only analytics views + SELECT-only Postgres role) and `db/seed_accounts.sql`. Enable pgvector. Run `corpus_ingest.sql`. Load `breakdown_history.json`, `spares`, `equipment`, `sensor_readings.csv`.
- **INTEGRATE:** FastAPI `lifespan` opens the pooled connection; `auth/jwt_dep.py` verifies Supabase JWT.

### 5.2 Schemas (schema-first — do before tools)
`schemas/cards.py`: all Pydantic card models with `ConfigDict(extra='forbid')`. Mirror to `frontend/lib/schemas.ts`. These are the SLM constrained-decode targets AND the React card props.

### 5.3 Tools (each: TEST in isolation → INTEGRATE as governed tool)
Build and unit-test each before wrapping it with `governed_tool`:
- `tools/rag.py` (provided) — assert a fault-code query returns the right chunk with citation.
- `tools/ml_tools.py` — load artifacts from `backend/models`; assert `estimate_rul('sinter-fan-2')` returns ~9 days on the seeded data.
- `tools/deterministic.py` — priority matrix + procurement_rule + severity rules; pure functions, fully unit-tested (these MUST be exactly right).
- `tools/spares.py`, `tools/reports.py`.

### 5.4 Governed agent (provided governance.py)
- `charters.py`: AGENT_CHARTERS with `pipeline` tuples.
- `pipelines.py`: each agent = deterministic tool sequence (NOT a ReAct loop).
- `synthesis.py`: Ollama `format=schema` synthesis + repair.
- Compile the controller graph with the Postgres checkpointer (`thread_id = chat session id`).

### 5.5 Scheduler & proactive pipeline
`scheduler/health_scan.py`: APScheduler 30s → cached feature build → IsolationForest → RUL → UPSERT `equipment_health` → severity-rule alert → insert `alerts` (Realtime fires the toast).

### 5.6 CopilotKit endpoint
`copilotkit_endpoint.py`: CoAgents bridge; passes `threadId`; streams `delegations` + cards.

### ✅ VERIFICATION GATE 4 (backend)
- `pytest` green on deterministic tools.
- A scripted `graph.invoke` for "diagnose F3 fault 0247" returns a valid DiagnosisCard with real citations and an audit_log row per tool.
- The scheduler, run once manually, writes an `equipment_health` row and an alert for the fan.
**Do not start the frontend agent wiring until a graph.invoke produces a valid card end-to-end.**

---

## 6. PHASE 5 — FRONTEND (attention-seeking, hackathon-winning UI/UX)

### 6.1 Design system (build tokens + atoms FIRST)
`styles/tokens.css`: dark graphite `#0E1116` / panels `#161B22`; steel-blue `#4A90D9` primary; **molten-orange `#FF6A2B` reserved EXCLUSIVELY for live/critical**; status `#3FB68B/#E8B931/#E5484D`. Mono (JetBrains/IBM Plex) for ALL telemetry/IDs/codes/RUL/timestamps; Inter for UI. Build the 9 atoms before any screen: StatusBadge, RiskPill, RulCountdown, EvidenceChip, SparesChip, AgentByline, SessionRow, ApprovalPrompt, SqlCard.

### 6.2 The signature: Evidence Trail
Under every AI claim, a chip row (`📄 SOP-HSM-114 §3.2 · 📈 14d trend · 🕓 BR-2023-0847 · ⚙ priority matrix`) → click opens the Evidence Drawer with the exact excerpt/chart/record. This is the single most memorable element — invest in it.

### 6.3 Screens (build in scenario order)
Plant Overview (zone-map plant-flow grid, KPI strip with ₹ downtime-at-risk, live alert feed) → Equipment Detail (health header, the showpiece SensorTrend chart with molten-orange anomaly markers + labeled threshold line + RUL panel, tabs History/Spares/Docs/Past Conversations) → Copilot sidebar (chat, session history, delegation stream, ApprovalPrompt) → Priority Board (ranked rows + score-breakdown drawer + what-if) → Reports & Logbook → Admin Console + /simulate.

### 6.4 Innovation beats (the little creativity — KEEP within PS scope)
- **Live agent-delegation stream** rendering CoAgents state ("→ Planner Agent: checking SKF 22230 lead time…") — turns architecture into visible trust.
- **Close-browser-and-resume** session demo (persistent multi-turn memory on camera).
- **Approve/Reject HITL** card ("agents propose; humans commit; everything is audited").
- **/simulate "stage director"** panel firing the live anomaly on cue.
- **Verified-fix green chip** appearing on a later similar query (continuous learning, visible).
- Subtle motion only where it carries meaning: 300ms animated re-rank on what-if; soft pulse on a critical tile; molten-orange live sensor cursor. No decorative animation.

### ✅ VERIFICATION GATE 5 (frontend)
- Login → role-aware landing works for both seeded accounts.
- Scenario A runs end-to-end in the UI: fault tile → diagnosis card → evidence chip opens → checklist → "✓ fixed it" → session resumes after browser close.
**Do not start Scenario B/C polish until A is clean including resume.**

---

## 7. PHASE 6 — INTEGRATION, OBSERVABILITY, FALLBACKS

- **Langfuse:** CallbackHandler on every `graph.invoke`; `session_id`/`user_id` set; verify the multi-agent trace tree appears (screenshot for submission). https://langfuse.com/integrations/frameworks/langgraph
- **DEMO_MODE cache:** top of the lookup chain — exact-match cached cards for every scripted demo query, so a live failure never shows a spinner-of-death.
- **Edge states:** loading/empty/error for every screen (judges will click wrong things).
- **Feedback loop round-trip:** 👍/👎/✓-fixed → DB + store + Langfuse score + verified re-embed → green chip on a later query.

### ✅ VERIFICATION GATE 6 (integration)
All three scenarios run start-to-finish with Langfuse traces and DEMO_MODE fallback armed.

---

## 8. PHASE 7 — ⭐ OPTIONAL ENHANCEMENT (only if Gates 1–6 all pass)

`tools/analytics.py` — governed text-to-SQL: SELECT-only role on read-only views (`v_breakdown_stats` etc.), LangChain SQLDatabaseToolkit with few-shot, EXPLAIN-validate, SqlCard (visible SQL = citation), guardrails `sql_is_select_only · whitelisted_views · numbers_match_rows`. Demo only if SLM SQL is reliable in rehearsal; else route this one tool to hybrid. https://python.langchain.com/docs/tutorials/sql_qa/

---

## 9. DEPLOYMENT (the honest split — do not fight serverless)

- **Frontend → Vercel** (native). https://vercel.com/docs
- **Stateful backend (graph, scheduler, ML, RAG) → always-on container** (Railway/Render/Fly) OR the dev laptop. Vercel Functions are stateless/500MB/≤500ms-shutdown — they CANNOT host the scheduler, Ollama SLM, or warm models. https://vercel.com/docs/functions/limitations
- **SLM → Ollama on the RTX 3060 + cloudflared tunnel** (on-prem story + offline demo). https://github.com/cloudflare/cloudflared
- **Postgres/Auth/Realtime → Supabase cloud.** https://supabase.com/docs
- For the demo: frontend on Vercel + full backend+Ollama on the laptop via tunnel + Supabase. Containerize at the end (`docker-compose.yml`) for the submission ZIP.
- (Optional) stateless edge routes may use the Vercel FastAPI pattern (`app` at entrypoint, `lifespan` for DB). https://vercel.com/docs/frameworks/backend/fastapi

---

## 10. ENV & SECRETS (`.env`)
> **Secrets redacted.** Real values live ONLY in the gitignored `.env` (see `.env.example` for the
> documented template). The original keys that appeared here in plaintext must be treated as
> compromised and **rotated** in the Supabase dashboard (see README → Security).
```
# Supabase
NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<redacted>
SUPABASE_ANON_KEY=<redacted>
SUPABASE_SERVICE_ROLE_KEY=<redacted>          # server-only
SUPABASE_JWT_SECRET=<redacted>
DATABASE_URL=postgresql://postgres:<password>@<host>:5432/postgres   # pooler URI
# Models
MODEL_BACKEND=slm_only            # slm_only | hybrid
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b-instruct  # qwen-forgesight once fine-tuned
EMBED_MODEL=nomic-embed-text
HOSTED_LLM_API_KEY=               # dev-time (SFT gen, DeepEval judge) + hybrid fallback only
# Obs / dev tools
LANGFUSE_PUBLIC_KEY=  LANGFUSE_SECRET_KEY=  LANGFUSE_HOST=https://cloud.langfuse.com
FIRECRAWL_API_KEY=<redacted>      # dev-time corpus seeding only (optional)
KAGGLE_USERNAME=<redacted>  KAGGLE_KEY=<redacted>    # dataset download (optional)
# Flags
DEMO_MODE=true
```

---

## 11. PS REQUIREMENT CHECKLIST (every item must map to a built feature)

| PS | Built by |
|---|---|
| §4.1 inputs (logs/faults/reports/incidents) | breakdown_history + alerts + fault-code chat entry |
| §4.2 sensor/anomaly/process inputs | sensor_readings + replayer + IsolationForest |
| §4.3 manuals/SOPs/records/spares | 3-mode retrieval: RAG (manual/sop) · match_history · check_spares SQL |
| §4.4 NL multi-turn | CopilotKit + checkpointed sessions + timestamped resumable history |
| §5.1 diagnosis/RCA/RUL/early-warning/defect | DiagnosisCard · RUL panel · severity rules · LightGBM defect (ml/defect) |
| §5.2 risk/urgency/bottleneck/prioritization | RiskPill · Supervisor Agent · Priority Board + auditable matrix drawer |
| §5.3 steps/immediate/plan/monitoring/procurement | ChecklistCard (LOTO-first) · wait-assessment · Planner procurement callout + HITL |
| §5.4 reports/alerts/summaries/logbook | ReportLab PDFs · alert report · shift summary · logbook |
| FR-1 LLM/SLM + fine-tune merit | SLM-first runtime, fine-tuned Qwen carries all reasoning (finetune/) |
| FR-2 integrate/reason over docs/logs | 3-mode retrieval incl. governed text-to-SQL · Docs tab |
| FR-3 context-aware multi-turn | sidebar + checkpoints + route context + resume-across-logins |
| FR-4 explainable/traceable | Evidence Trail + citation-existence guardrail + matrix-provenance + Langfuse |
| FR-5 anomaly/early-warning/prediction | scheduler + IsolationForest + RUL + severity rules (ml/) |
| FR-6 feedback loop | 👍/👎/✓-fixed → store + score + verified re-embed → green chip |
| FR-7 realtime alerts | Realtime role-filtered toasts + alert report |
| §7 optional (UI/dashboard/IoT-sim/KB/logbook/roles) | Copilot · Plant Overview · /simulate · per-equipment corpus · auto logbook · 2-role + agents |
| §8 outcomes | demo narrative + ₹-at-risk + metrics tables + on-prem/₹0-cost story |
| §9 deliverables | repo + docs/architecture.md + README (credentials/install) + sample_io + recording → ZIP |
| auth/validation/verification | 3-tier trust: Supabase JWT+RLS · agent charters/budgets/HITL/audit · guardrails |

---

## 12. GOLDEN RULES (do not violate)
1. Datasets and corpus before ML; ML artifacts before tools; tools before agent; agent before frontend wiring; Scenario A clean before B/C.
2. Deterministic tools (priority matrix, severity, procurement) are pure code, fully unit-tested, never LLM-generated.
3. Every AI claim carries a citation that EXISTS in retrieved context — the guardrail enforces this; never weaken it.
4. The SLM never selects tools (pipelines do) and never computes numbers (tools do); it only narrates and fills schemas under constrained decoding.
5. COMMIT-class actions always pass the human_gate. Agents propose; humans commit; everything is audited.
6. Keep the demo offline-capable; arm DEMO_MODE; drive live events from /simulate.
7. Train/serve parity: one `feature_config.json`, one `prompt_builder.py`, shared between notebooks and backend.
