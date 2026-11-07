# Production Dockerfile for the FastAPI + PostgreSQL stack this project targets.
# NOT built or run in the sandbox this project was developed in (no Docker daemon available -
# see docs/adr/ADR-002 and ADR-003 for why the sandbox build substitutes SQLite/Flask instead).
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for psycopg (PostgreSQL) and geo libraries used by GeoAlchemy2/Shapely in the
# production stack.
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpq-dev gcc curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-production.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY migrations/ ./migrations/

ENV PYTHONPATH=/app/src
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8000/healthz || exit 1

# Production entrypoint once the FastAPI layer replaces the sandbox's Flask layer:
CMD ["uvicorn", "agrotrust.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
