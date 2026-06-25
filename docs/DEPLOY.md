# ForgeSight — Deployment (Vercel frontend + Railway backend)

The production split: **frontend → Vercel**, **stateful backend (graph + scheduler + ML) →
Railway.app**, **Postgres+pgvector → Supabase**. The backend Docker image uses `backend/Dockerfile`.

## 0. One-time prerequisites
```bash
railway login                # opens a browser (interactive) — or export RAILWAY_API_TOKEN=...
vercel login                 # already authenticated as gurjas2112 in this environment
```

## 1. Backend → Railway.app
```bash
# from repo root (railway.json points build → backend/Dockerfile)
railway init --name forgesight
railway add --service forgesight-api
railway service forgesight-api

# --- Database (Supabase Postgres + pgvector) ---
# Use the Supabase Session pooler URI (IPv4, port 5432):
railway variable set DATABASE_URL="postgresql://postgres.<ref>:<pw>@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres"

# --- Secrets ---
railway variable set \
  SUPABASE_URL="https://<ref>.supabase.co" \
  SUPABASE_SERVICE_ROLE_KEY="eyJ..." \
  SUPABASE_JWT_SECRET="..." \
  LLM_API_KEY="sk-..." \
  SYNTHESIS_BACKEND="hosted" \
  LLM_PROVIDER="groq" \
  LLM_MODEL="llama-3.3-70b-versatile" \
  RETRIEVAL_MODE="fulltext" \
  MODEL_BACKEND="slm_only" \
  DEMO_MODE="true" \
  ALLOWED_ORIGINS="https://forge-sight-one.vercel.app,http://localhost:3000" \
  PORT="8080"

# --- Schema + seeds + health scan (run once against the prod DB) ---
python backend/db/apply_migrations.py        # schema + RLS + seeds + corpus + sensors
python backend/scheduler/health_scan.py --once   # equipment_health + CRITICAL fan alert

# --- Deploy ---
railway up --detach
railway domain    # generates https://forgesight-production.up.railway.app
```

Backend env: `SYNTHESIS_BACKEND=hosted`, `RETRIEVAL_MODE=fulltext`,
`ALLOWED_ORIGINS` includes `https://forge-sight-one.vercel.app`. With no LLM quota the public URL
still serves the **golden demo cache** (scripted F3 diagnosis + fan wait-assessment) and all
DB-backed endpoints (`/equipment`, `/alerts`, `/evidence`, `/reports/*`, deterministic cards).

## 2. Frontend → Vercel
```bash
cd frontend
vercel link --project prj_bagyErlJEr4cYV2DAuAzv2178Q5X
```

**Critical (monorepo):** In the [Vercel project settings](https://vercel.com/gurjas2112s-projects/forge-sight/settings),
set **Root Directory** to `frontend`, then **Redeploy** from the latest `main` commit (GitHub is already
connected). Without this, builds run at the repo root and production returns 404.

Set **production** env vars (Project → Settings → Environment Variables):
vercel env add NEXT_PUBLIC_API_URL production   # value: https://forgesight-production.up.railway.app
vercel env add NEXT_PUBLIC_SUPABASE_URL production
vercel env add NEXT_PUBLIC_SUPABASE_ANON_KEY production
vercel --prod
```

## 3. Verify the live demo
`https://forge-sight-one.vercel.app` → Landing page → Login (demo engineer) → Plant Overview
(F3 critical tile) → F3 detail → "diagnose the F3 trip" → DiagnosisCard + Evidence drawer →
Sinter Fan #2 → "can it wait till Sunday?" → WaitAssessment + Approve. Browser network calls
should hit `forgesight-production.up.railway.app` with no CORS errors.

## Live URLs
- **Frontend:** https://forge-sight-one.vercel.app
- **Backend:** https://forgesight-production.up.railway.app
- **Health check:** https://forgesight-production.up.railway.app/healthz

## Notes
- The Docker image excludes `data/`, `ml/`, `finetune/`, `frontend/` (see `.dockerignore`) — only
  `backend/` + the serve-time `backend/models/*` artifacts ship (~600 MB).
- Rotate `LLM_API_KEY` and the Supabase secrets after the hackathon.
- Cloud synthesis uses the OpenAI fallback; the golden demo cache covers scripted scenarios
  regardless of LLM quota status.
