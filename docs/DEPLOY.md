# ForgeSight — Deployment (Vercel frontend + Fly.io backend)

The production split (per `forgesight-v3-final.md §1.12`): **frontend → Vercel**, **stateful
backend (graph + scheduler + ML) → Fly.io**, **Postgres+pgvector → Fly Postgres or Supabase**.
The backend Docker image is validated locally (`docker build -f backend/Dockerfile .`).

## 0. One-time prerequisites
```bash
flyctl auth login            # opens a browser (interactive) — or export FLY_API_TOKEN=...
vercel login                 # already authenticated as gurjas2112 in this environment
```

## 1. Backend → Fly.io
```bash
# from repo root (fly.toml is here; it points build → backend/Dockerfile)
flyctl apps create forgesight          # or: flyctl launch --no-deploy --copy-config

# --- Database (choose ONE) ---
# A) Fly Postgres (needs a card on the Fly org):
flyctl postgres create --name forge-sight-db --region iad --vm-size shared-cpu-1x --volume-size 1
flyctl postgres attach forge-sight-db -a forgesight     # sets DATABASE_URL secret
#    then enable pgvector once: flyctl postgres connect -a forge-sight-db -c "CREATE EXTENSION IF NOT EXISTS vector;"
# B) Supabase (no Fly billing; pgvector built-in) — set the pooler URI yourself:
flyctl secrets set DATABASE_URL="postgresql://postgres.<ref>:<pw>@aws-0-<region>.pooler.supabase.com:6543/postgres" -a forgesight

# --- Secrets (synthesis fallback) ---
flyctl secrets set LLM_API_KEY="sk-..." -a forgesight   # OpenAI key (needs billing/quota for live synthesis)

# --- Schema + seeds + health scan (run once against the prod DB) ---
#  point a local shell at the prod DB URL and run the same idempotent scripts:
export DATABASE_URL="<the prod url>"
python backend/db/apply_migrations.py        # schema + RLS + seeds + corpus + sensors + analytics views
python backend/scheduler/health_scan.py --once   # equipment_health + the CRITICAL fan alert

# --- Deploy ---
flyctl deploy -a forgesight
flyctl status -a forgesight
curl https://forgesight.fly.dev/healthz   # {"ok":true,"db":true,...}
```

Backend env (already in `fly.toml`): `SYNTHESIS_BACKEND=hosted`, `RETRIEVAL_MODE=fulltext`,
`ALLOWED_ORIGINS` includes `https://forge-sight-one.vercel.app`. With no LLM quota the public URL
still serves the **golden demo cache** (scripted F3 diagnosis + fan wait-assessment) and all
DB-backed endpoints (`/equipment`, `/alerts`, `/evidence`, `/reports/*`, deterministic cards).

## 2. Frontend → Vercel
```bash
cd frontend
vercel link --project prj_bagyErlJEr4cYV2DAuAzv2178Q5X   # links to the existing forge-sight-one project
vercel env add NEXT_PUBLIC_API_URL production            # value: https://forgesight.fly.dev
vercel --prod
```
If the Vercel project auto-deploys from GitHub `main`, instead set `NEXT_PUBLIC_API_URL` in the
Vercel dashboard (Project → Settings → Environment Variables) and push the `frontend/` changes to
`main` to trigger a build.

## 3. Verify the live demo
`https://forge-sight-one.vercel.app` → Plant Overview (F3 critical tile) → F3 detail →
"diagnose the F3 trip" → DiagnosisCard + Evidence drawer → Sinter Fan #2 → "can it wait till
Sunday?" → WaitAssessment + Approve. Browser network calls should hit `forgesight.fly.dev`
with no CORS errors.

## Notes
- Single worker keeps the LangGraph controller + pool warm; `min_machines_running = 1` avoids
  cold starts during judging.
- The image excludes `data/`, `ml/`, `finetune/`, `frontend/` (see `.dockerignore`) — only
  `backend/` + the serve-time `backend/models/*` artifacts ship (~600 MB).
- Rotate `LLM_API_KEY` and the BUILD_GUIDE §10 secrets after the hackathon.
