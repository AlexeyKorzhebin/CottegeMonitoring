FROM python:3.12-slim AS builder

WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .

FROM python:3.12-slim

WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY src/ src/
COPY alembic/ alembic/
COPY alembic.ini .

ENV PYTHONUNBUFFERED=1
ENV API_PORT=8321
EXPOSE 8321

CMD ["sh", "-c", "exec uvicorn cottage_monitoring.main:app --host 0.0.0.0 --port ${API_PORT}"]
