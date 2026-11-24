# Build from the repository root:  docker build -f apps/api/Dockerfile -t slatehire-api .
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY packages/core-py /app/packages/core-py
COPY apps/api /app/apps/api
COPY data /app/data
RUN pip install --no-cache-dir /app/packages/core-py "/app/apps/api[postgres]"
ENV SEED_DIR=/app/data EXPORT_DIR=/data/exports
RUN useradd --create-home --uid 10001 app && mkdir -p /data/exports && chown -R app /data
USER app
WORKDIR /app/apps/api
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health')"
# Migrations run on start for Postgres. SQLite creates its own tables.
CMD ["sh", "-c", "case \"$DATABASE_URL\" in postgres*) alembic upgrade head;; esac; exec python -m uvicorn slatehire.api.app:app_from_env --factory --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*'"]
