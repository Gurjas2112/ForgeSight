# ForgeSight — End-to-End Verification Report

**Date:** 2026-06-16 · **Branch:** `main` · **Method:** every claim re-run locally or probed live
against the deployed stack (not asserted from memory).

**Verdict:** ✅ All checklist items PASS. One class of genuine breakage was found and fixed
(dead documentation links to deleted design docs). Two benign deviations and one stale-doc note
are recorded below for awareness.

---

## 1. Local ML deliverables — PASS

| Model | test.csv | submission.csv | dims match | key |
|---|---|---|---|---|
| anomaly | 17280×13 | 17280×3 | ✅ | window_id |
| failure_classifier | 2000×6 | 2000×3 | ✅ | id |
| rul | 100×47 | 100×2 | ✅ (100 rows) | unit |
| defect | 389×29 | 389×3 | ✅ | id |
| azure_pdm | 73900×21 | 73900×3 | ✅ | id |

- `dimensions.json` row/col counts match the actual CSVs for all 5 models; `submission` rows ==
  `test` rows everywhere; RUL submission is exactly 100 rows (C-MAPSS FD001 test units).
- `ml/README.md` dimensions table matches `dimensions.json` exactly.
- **Determinism:** re-ran `python ml/failure_classifier/train.py` (seed=42, ~23s) → regenerated
  `submission.csv`/`test.csv` and the served `backend/models/failure_xgb_v1.json` were **byte-identical**
  (`md5` unchanged, empty `git status`). Reproducible deliverable confirmed.

## 2. bearing_features — PASS
- `python ml/bearing_features/extract_features.py` ran on the committed `sample_de.csv` with **no
  Kaggle**, wrote `bearing_features.csv` (40 windows × 7), kurtosis −1.45→18.87 as documented;
  output byte-identical to committed (deterministic).

## 3. Fine-tune pipeline — PASS
- `generate_sft.py` → 214 train + 23 eval pairs; `quality_gates.py` → **237 pass / 0 fail (PASS)**,
  exit 0. Regenerated JSONL byte-identical to committed. Base Qwen ships per the locked decision;
  pipeline is fully evidenced.

## 4. Local backend — PASS
- `pytest backend/tests -q` → **28 passed in 1.25s** (deterministic, feedback_loop, guardrails,
  prompt_builder).
- F3 golden path: `golden_demo_cache()["hsm-f3-stand::diagnose the f3 trip"]` is a `diagnosis` card
  citing **BR-2024-0312** (+ BR-2024-0155, SOP-HSM-ELEC-09). ✅

## 5. Frontend build / type-check — PASS
- `npx tsc --noEmit` clean (exit 0).
- `next build` succeeded: compiled, TypeScript passed, 6 routes built
  (`/`, `/dashboard`, `/equipment/[id]`, `/login`, `/signup`).
- NOTE (benign): build warns about an inferred workspace root from a stray
  `C:\Users\Gurjas Gandhi\package-lock.json`; cosmetic, set `turbopack.root` to silence.

## 6. Deployed backend (Railway) — PASS
Base URL: `https://forgesight-production.up.railway.app`
- `GET /healthz` → `{"ok":true,"db":true,"synthesis_backend":"hosted","model":"groq:llama-3.3-70b-versatile","scheduler":true}`
- `GET /equipment` → live list (caster-1, hsm-f3-stand, …) with anomaly scores + RUL.
- `GET /alerts` → CRITICAL `sinter-fan-2` (anomaly 0.626, RUL ≈ 3.3d).
- `GET /models/scorecard` → live model metrics.
- `POST /chat` (F3 diagnosis, no token → demo engineer) → **HTTP 200, live Groq synthesis**,
  diagnosis card with root cause "Braking resistor element open-circuit" citing **BR-2024-0312**
  (de-canned live pipeline, not the golden cache).
- **CORS:** `OPTIONS /chat` with `Origin: https://forge-sight-one.vercel.app` →
  `access-control-allow-origin: https://forge-sight-one.vercel.app`. No CORS barrier for the frontend.

## 7. Deployed frontend (Vercel) — PASS
Base URL: `https://forge-sight-one.vercel.app`
- Landing (`/`) HTTP 200, renders hero "fault code to fix plan" + Login/Signup CTAs.
- `/login` HTTP 200 with prefilled `engineer@demo.forgesight`; `/dashboard` shell HTTP 200.
- Deployed JS bundle has both `forgesight-production.up.railway.app` and
  `djmkavlurexdezyvvhcu.supabase.co` inlined → correctly wired to the Railway backend + Supabase auth.
- **Auth flow proven without a browser:** Supabase password login for the seeded **engineer** and
  **admin** both issue valid ES256 JWTs; backend `GET /auth/me` decodes them to
  `{"role":"engineer"}` and `{"role":"admin"}` respectively → login + role-badge path verified.
- Remaining manual step: the interactive UI click-through (type creds → click → see DiagnosisCard +
  Evidence drawer). Every underlying component is confirmed; only the human click is un-automated.

## 8. Requirements traceability — PASS (after fix)
- Spot-checked every file/endpoint referenced by `docs/requirements_traceability.md`: all backend
  modules (`synthesis.py`, `rag.py`, `text_to_sql.py`, `governance.py`, `health_scan.py`,
  `reports.py`, `feedback_store.py`, `pipelines.py`), tests, and `finetune/{colab_train,
  03_evaluate_vs_base}.py` exist. FR-1 (Groq hosted), FR-4 (citations), FR-5 (alerts),
  FR-6 (`/feedback`), FR-7 (scheduler) confirmed live against the deployed backend.

---

## Fixes applied (this pass)
**Genuine breakage: dead links to deleted design docs.** The most recent commit (9b935fe,
*"after deletion of files and shifting…"*) deleted the monolithic `forgesight-v3-final.md` and
`BUILD_GUIDE.md` (content split into `docs/*.md`) but left dangling references — including
`docs/architecture.md` redirecting to a now-missing "authoritative architecture document," which
broke the PS §9 architecture deliverable. Repointed all references to the docs that actually exist;
no dead `forgesight-v3-final` / `BUILD_GUIDE` / `sft-dataset-spec` links remain:
- `docs/architecture.md` — made self-authoritative; links to sibling `docs/*.md`.
- `docs/requirements_traceability.md` — §9 row → `docs/architecture.md`, `docs/finetune.md`.
- `README.md` (×3) — design/build pointers and the security note repointed.
- `finetune/README.md`, `ml/README.md`, `data/raw/azure_pdm/README.md` — dead `BUILD_GUIDE §N`
  pointers removed/repointed.

## Notes / benign deviations (not breakage — recorded, not changed)
- **Railway + Supabase, not Fly.io.** Backend runs on Railway (`railway.json`), DB + Auth on
  Supabase. The original plan explicitly allowed Supabase as the pgvector fallback; no `fly.toml`
  by design.
- **Client-side `AuthGuard`, not `@supabase/ssr` middleware.** Route protection is the browser
  Supabase client + `AuthGuard` wrapper rather than Next middleware. Functionally equivalent for
  this SPA-style frontend; `@supabase/ssr` is not installed.
- **`data/raw/azure_pdm/README.md` framing.** It still describes the Azure PdM data as a "schema
  template." Since the mid-execution update, `ml/azure_pdm/` is a **real trained XGBoost model**
  (PR-AUC 0.899) using the downloaded `PdM_*.csv`. The dead-link fix removed the inaccurate "not
  used by any code path" clause, but the "template" header could be refreshed to reflect that the
  model is now live if desired.

---

## Hardening pass — 2026-06-16 (remove the 4 flagged weaknesses)

A follow-up critique flagged four credibility weaknesses. All addressed; verified locally
(`pytest backend/tests -q` → **37 passed**; `npx tsc --noEmit` clean; `next build` clean;
`GET /plant/summary` live against Supabase, deterministic).

1. **Real computed dashboard KPIs** (was `92%` / `₹18L` hardcoded). New pure `backend/tools/
   plant_summary.py` + `GET /plant/summary`. Live values: **availability 84.3%**, **1 asset
   alerting** (deduped from 140 raw scheduler rows), **at-risk 1**, **₹13L** downtime-at-risk —
   all derived from `equipment_health` + `v_downtime_by_equipment` + open alerts, with the cost
   assumption returned in the `assumptions` field. Re-call identical. Unit-tested
   (`backend/tests/test_plant_summary.py`).
2. **Honest agent activity** (was a fabricated `setTimeout` "thinking" stream in `Sidebar.tsx`).
   Removed; replaced with a neutral "Running governed pipeline…" busy indicator. The real
   `delegations` from the graph still render.
3. **Auth hardening** (was: public signup could self-assign `admin`). `POST /auth/signup` now
   downgrades an `admin` request to `engineer` unless a valid admin Bearer token is present;
   `require_admin` dependency added; the frontend signup role selector removed. Pinned by
   `backend/tests/test_auth_gating.py`. Backend JWT verification remains the enforced boundary.
4. **Digital-twin transparency** (synthetic data is now an owned, labelled choice). "Digital twin ·
   simulated sensors" badge on the dashboard + equipment headers; explicit twin framing in the
   landing hero/CTA; documented in `assumptions_limitations.md`.

**Note:** these changes are verified locally; the public Vercel/Railway URLs reflect them only after
a redeploy (Railway backend + `vercel --prod`), which needs the user's deploy auth.
