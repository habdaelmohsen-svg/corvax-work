FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json frontend/.npmrc ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000
WORKDIR /app
RUN useradd --create-home --uid 10001 corvax
# AUDIT H-03: pg_dump must exist inside the image or the backup endpoint answers
# 501 on PostgreSQL. postgresql-client is small and makes backups actually work.
RUN apt-get update \
 && apt-get install --no-install-recommends -y postgresql-client \
 && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt
COPY --chown=corvax:corvax backend/ ./
COPY --from=frontend-build --chown=corvax:corvax /app/frontend/dist ./static
RUN mkdir -p /app/data /app/data/backups && chown -R corvax:corvax /app
USER corvax
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)" || exit 1
STOPSIGNAL SIGTERM
# Database migrations run at container start. Render's Pre-Deploy Command is a
# paid feature, so the schema upgrade is performed here instead. Alembic skips
# revisions that are already applied, so this is safe on every restart, and the
# server only starts if the upgrade succeeds.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
