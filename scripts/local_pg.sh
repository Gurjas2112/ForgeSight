#!/usr/bin/env bash
# ForgeSight — ephemeral local Postgres + pgvector for end-to-end verification WITHOUT the
# Supabase DB password. Prints the DATABASE_URL to export for apply_migrations + diagnose_f3.
set -euo pipefail

NAME=forgesight-pg
IMAGE=pgvector/pgvector:pg16
PORT=5433
PASS=forgesight
DB=forgesight

docker rm -f "$NAME" >/dev/null 2>&1 || true
echo "starting $IMAGE as $NAME on :$PORT …"
docker run -d --name "$NAME" \
  -e POSTGRES_PASSWORD="$PASS" -e POSTGRES_DB="$DB" \
  -p "$PORT":5432 "$IMAGE" >/dev/null

echo -n "waiting for postgres"
for _ in $(seq 1 30); do
  if docker exec "$NAME" pg_isready -U postgres >/dev/null 2>&1; then echo " — ready"; break; fi
  echo -n "."; sleep 1
done

echo ""
echo "DATABASE_URL=postgresql://postgres:${PASS}@localhost:${PORT}/${DB}"
echo ""
echo "Next:"
echo "  export DATABASE_URL=postgresql://postgres:${PASS}@localhost:${PORT}/${DB}"
echo "  uv run python backend/db/apply_migrations.py"
echo "  uv run python scripts/diagnose_f3.py"
echo "Teardown: docker rm -f $NAME"
