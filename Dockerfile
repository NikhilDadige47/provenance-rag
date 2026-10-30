# syntax=docker/dockerfile:1
# One public host: React SPA is built into frontend-react/dist and FastAPI serves
# it at the same origin as /session, /chat, /upload, /health.

FROM node:22-alpine AS frontend
WORKDIR /ui
COPY frontend-react/package.json frontend-react/package-lock.json ./
RUN npm ci
COPY frontend-react/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md TERMS.md ./
COPY src ./src
COPY demo_corpus ./demo_corpus
COPY eval/golden_set.jsonl ./eval/golden_set.jsonl
COPY scripts ./scripts
COPY --from=frontend /ui/dist ./frontend-react/dist

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

ENV APP_ENV=production \
    DATA_DIR=/data \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

RUN mkdir -p /data
EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
