# ForgeSight backend — FastAPI governed graph (deploy target: Fly.io).
# Build context = repo root:  docker build -f backend/Dockerfile -t forgesight-api .
# Ollama is NOT baked in; on Fly set SYNTHESIS_BACKEND=hosted (+ LLM_API_KEY) and
# RETRIEVAL_MODE=fulltext so synthesis/embeddings don't need a local SLM.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

# libgomp1 is required by lightgbm (served defect pipeline) and xgboost wheels.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --upgrade pip && pip install -r backend/requirements.txt

# App package + serve-time ML artifacts (backend/models/*.joblib,*.json).
COPY backend/ ./backend/

EXPOSE 8080
# Honor Fly's $PORT (defaults to 8080); single worker keeps the controller/pool warm.
CMD ["sh", "-c", "uvicorn backend.server:app --host 0.0.0.0 --port ${PORT:-8080}"]
