# ForgeSight — Assumptions & Limitations (PS §9)

## Framing
**Benchmarks validate the method; the simulation validates the system.** ML methods are trained
and scored on real public run-to-failure / fault datasets (NASA C-MAPSS, AI4I 2020, UCI Steel
Plates, CWRU/IMS bearings); the integrated maintenance system is demonstrated on a physics-informed
**digital twin** of a steel plant (6 equipment, injected fan-bearing degradation + an F3 VFD trip),
because no real steel-plant sensor stream is publicly available. The twin is labelled as such in the
UI (dashboard + equipment headers, landing copy) — the simulated sensors are an owned design choice;
the governance, ML inference, and reasoning that run on top of them are real.

## Assumptions
- **Synthetic sensor layer.** 30 days × 5-min readings per equipment; the sinter-fan degradation
  *shape* is borrowed from a NASA IMS run-to-failure trajectory. Fault codes/dates are aligned with
  the breakdown corpus (BR-2024-0312 etc.).
- **RUL serving = trend extrapolation.** At serve time RUL is a Tier-1 linear extrapolation of
  vibration to the next limit (alarm 7.1 → trip 11.0 mm/s). The XGBoost C-MAPSS model (RMSE 16.4,
  by-unit split) validates the *regression method*; it is not the per-fan serving path because the
  fan and turbofan feature spaces differ.
- **Corpus scope.** Pass-1 corpus = synthetic LOTO-first SOPs + breakdown records (9 chunks). Real
  OEM PDFs (ABB ACS880 / SKF) drop into `data/synthetic/manuals/` to expand `doc_type=manual`
  coverage; the pipeline already handles them.
- **Demo accounts** are seeded pre-confirmed (`engineer@demo` / `admin@demo`); email verification
  is ON for self-registration, OFF for seeds — stated prototype posture.
- **Public signup is engineer-only.** `POST /auth/signup` only mints the `engineer` role for
  unauthenticated callers; an `admin` request is downgraded unless a valid admin Bearer token is
  presented (`require_admin`). Admin accounts are provisioned by an administrator / the seeder. The
  enforced security boundary is backend JWT verification on every request (`backend/auth/jwt.py`),
  not the client-side `AuthGuard` (which is UX-only).

## Limitations
- **Anomaly precision.** IsolationForest favours recall (1.0, 8.7 d lead time) over precision
  (~0.23 on the labelled window) — appropriate for early warning, but it over-flags; production
  would add sustained-window confirmation (the severity rule already requires 3 windows).
- **Fine-tune (hybrid serving).** The SFT pipeline (parity serializer, expanded card-target pairs
  incl. RUL/priority/spares/wait-assessment, quality gates, Unsloth QLoRA) ships a one-file Colab T4
  runner `finetune/colab_train.py` → GGUF → `ollama create qwen-forgesight`. **Locally** the
  fine-tuned Qwen serves synthesis (`SYNTHESIS_BACKEND=ollama`, `OLLAMA_MODEL=qwen-forgesight`);
  **publicly** Railway has no GPU so it uses the **Groq** fallback. `/healthz` reports the active
  backend+model. Promotion is gated by `finetune/03_evaluate_vs_base.py` (citation + number
  fidelity); base Qwen is the sanctioned fallback (citation compliance is structural either way).
- **CopilotKit.** The conversational sidebar implements the CoAgents pattern (delegation stream,
  cards, HITL approval, Evidence Trail) with a reliable direct-to-API transport rather than the
  CopilotKit runtime, to stay compatible with Next.js 16 / React 19 under the deadline.
- **Deployment.** Frontend → Vercel, stateful backend → Railway (Docker image validated), Postgres
  +pgvector → Supabase (`docs/DEPLOY.md`). On the cloud backend there is no local
  Ollama, so synthesis uses the **Groq hosted fallback** (`SYNTHESIS_BACKEND=hosted`,
  `LLM_PROVIDER=groq`, `llama-3.3-70b-versatile` via OpenAI-compatible API) and RAG runs
  **full-text-primary** (`RETRIEVAL_MODE=fulltext`) — citations stay real (chunks come from the DB).
  The demo is **de-canned**: `DEMO_MODE` defaults false, so `/chat` runs the real governed pipeline
  and the golden card only appears as an **error/timeout fallback**; locally synthesis runs live on
  Ollama Qwen2.5-3B (the fine-tuned `qwen-forgesight` when promoted).
- **Real ML inference + scorecard.** `GET /models/scorecard` (and the dashboard panel) run **live
  held-out inference** per model: anomaly (live on sensors), defect (live LightGBM on a real Steel
  Plates row — the former zero-vector stub is gone), and failure/Azure/RUL (live XGBoost on their
  committed held-out rows). failure/Azure/RUL are **benchmark-validated second opinions**, not
  per-equipment sensor models — we do not fabricate a sensor→feature mapping that doesn't hold.
- **Feedback loop (FR-6).** `/feedback` is feedback-conditioned retrieval + few-shot exemplar
  injection (`backend/tools/feedback_store.py`), NOT weight retraining: a `down` verdict demotes the
  cited record on re-ask, a `fixed` verdict injects the confirmed cause into synthesis. In-process
  for the warm demo session + persisted to the DB `feedback` table; proven by `test_feedback_loop.py`.
- **Scheduler (FR-7).** The health re-scan runs inside the FastAPI `lifespan` behind
  `ENABLE_SCHEDULER` (asyncio task, `SCHEDULER_INTERVAL_SECONDS`, default 120 s) so `/alerts`
  reflects live re-scans — kept cheap for the Railway free tier.
- **Text-to-SQL (§1.7b).** `query_records` is template-first (deterministic, demo-safe) with an
  optional SLM pass validated by the same SELECT-only + whitelist + EXPLAIN guards, so an unreliable
  3B model can never emit an unsafe or hallucinated query; it reaches only four curated read-only views.
- **Plant KPIs are computed, not hardcoded.** The dashboard header (availability · assets alerting ·
  downtime-at-risk) is served by `GET /plant/summary` (`backend/tools/plant_summary.py`, pure +
  unit-tested). Availability = criticality-weighted share of plant capacity not under active downtime
  risk; downtime-at-risk = Σ(expected_downtime_hrs × `BASE_INR_PER_HR` × criticality) over at-risk
  assets, where expected hours come from `v_downtime_by_equipment` history (default 8 h). The
  `BASE_INR_PER_HR` cost rate is a **documented assumption** returned in the response's `assumptions`
  field, so the headline ₹ figure is traceable. Open-alert count is distinct alerting assets (the
  scheduler re-inserts each scan, so a raw row count would be noise).
- **Honest agent activity.** The copilot shows a neutral "Running governed pipeline…" indicator while
  a turn executes, then renders the **real** agent delegations returned by the graph — there is no
  scripted/fabricated "thinking" stream.
- **Scenarios.** A (diagnosis incl. Evidence Drawer), B (early warning, RUL, wait-assessment fan-out,
  HITL), C (priority, spares) are end-to-end. Now also: **FR-6 feedback** (verified-chip loop),
  **§5.4 PDF reports**, **§1.7b analytical text-to-SQL**. Admin Console / Plant `/simulate` UI screens
  and Langfuse tracing remain scoped out.
