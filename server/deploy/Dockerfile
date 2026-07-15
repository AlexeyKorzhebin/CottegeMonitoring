FROM python:3.12-slim AS builder

WORKDIR /app
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir .

FROM python:3.12-slim

WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY alembic/ alembic/
COPY alembic.ini .

ENV PYTHONUNBUFFERED=1

# Bind localhost by default — MCP/API are for same-host agents (OpenClaw), not the public internet.
CMD ["sh", "-c", "exec uvicorn cottage_monitoring.main:app --host ${API_HOST:-127.0.0.1} --port ${API_PORT:-8321}"]
