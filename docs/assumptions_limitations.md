# ForgeSight — Assumptions & Limitations (PS §9)

## Framing
**Benchmarks validate the method; the simulation validates the system.** ML methods are trained
and scored on real public run-to-failure / fault datasets (NASA C-MAPSS, AI4I 2020, UCI Steel
Plates, CWRU/IMS bearings); the integrated maintenance system is demonstrated on a physics-informed
synthetic steel layer (6 equipment, injected fan-bearing degradation + an F3 VFD trip), because no
real steel-plant sensor stream is publicly available.

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

## Limitations
- **Anomaly precision.** IsolationForest favours recall (1.0, 8.7 d lead time) over precision
  (~0.23 on the labelled window) — appropriate for early warning, but it over-flags; production
  would add sustained-window confirmation (the severity rule already requires 3 windows).
- **Fine-tune.** The SFT pipeline (parity serializer, 40 validated pairs, quality gates, Unsloth
  QLoRA script, base-vs-FT eval) is complete, but QLoRA training runs on Colab/GPU. The runtime
  ships **base Qwen2.5-3B** under constrained decoding (citation compliance is structural, not
  model-dependent) per the design's promotion rule; the fine-tune promotes only if it beats base on
  citation + number fidelity.
- **CopilotKit.** The conversational sidebar implements the CoAgents pattern (delegation stream,
  cards, HITL approval, Evidence Trail) with a reliable direct-to-API transport rather than the
  CopilotKit runtime, to stay compatible with Next.js 16 / React 19 under the deadline.
- **Deployment.** Demo runs locally (frontend + FastAPI + Ollama + local pgvector or Supabase).
  The honest production split (frontend → Vercel, stateful backend → always-on container, SLM →
  GPU host, Postgres → Supabase) is documented in `forgesight-v3-final.md §1.12`.
- **Scenarios.** A (diagnosis) is fully end-to-end incl. Evidence Drawer; B (early warning, RUL,
  wait-assessment fan-out, HITL) and C (priority, spares) are wired and demoable; Reports/Admin
  Console/Plant /simulate UI screens are scoped out of this build.
