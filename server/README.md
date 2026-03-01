# CottageMonitoring Server

FastAPI + MQTT Ingestor for cottage monitoring system. Receives telemetry from houses via MQTT, stores in PostgreSQL/TimescaleDB, caches current state in Redis, and exposes REST API for external systems.

## Architecture

Single asyncio event loop:
- FastAPI for REST API
- aiomqtt subscriber for MQTT ingestion
- Command retry scheduler (periodic check for timed-out commands)

## Tech Stack

- Python 3.12
- FastAPI, uvicorn
- aiomqtt
- SQLAlchemy 2.x (async), asyncpg
- PostgreSQL + TimescaleDB
- Redis
- Prometheus (metrics)
- structlog

## Server

- **Host**: elion.black-castle.ru
- **Production**: monitoring.black-castle.ru (port 8321)
- **Dev**: monitoring-dev.black-castle.ru (port 8322)

## Quick Start

### Local development (SSH tunnel)

```bash
# Terminal 1: SSH tunnel to elion (PostgreSQL, Redis, MQTT)
ssh -L 5432:localhost:5432 -L 6379:localhost:6379 -L 1883:localhost:1883 elion -N

# Terminal 2: Run server
cd server
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp deploy/cottage-monitoring.dev.env .env
alembic upgrade head
uvicorn cottage_monitoring.main:app --host 127.0.0.1 --port 8322 --reload
```

### Production (Docker + systemd on elion)

```bash
ssh elion
cd /opt/cottage-monitoring/server
sudo docker build -t cottage-monitoring:latest -f deploy/Dockerfile .
sudo cp deploy/cottage-monitoring.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable cottage-monitoring
sudo systemctl start cottage-monitoring
```

## API

- **Docs (Swagger UI)**: `/docs`
- **Health**: `/health`
- **Metrics**: `/metrics` (Prometheus; access restricted in nginx)

## Tests

```bash
cd server
pytest tests/unit/ -v
pytest tests/integration/ -v
pytest tests/contract/ -v
pytest -v
ruff check .
```

## Project Structure

```
server/
├── src/cottage_monitoring/
│   ├── main.py           # FastAPI app + lifespan (MQTT, retry loop)
│   ├── config.py
│   ├── logging_config.py
│   ├── metrics.py
│   ├── api/              # FastAPI routers
│   ├── models/           # SQLAlchemy ORM
│   ├── schemas/          # Pydantic schemas
│   ├── services/         # Business logic (ingestor, state, event, command, etc.)
│   ├── mqtt/             # aiomqtt client, topic parser
│   └── db/               # Async session
├── tests/
│   ├── unit/
│   ├── integration/
│   └── contract/
├── deploy/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── cottage-monitoring.service
│   ├── cottage-monitoring-dev.service
│   ├── nginx/cottage-monitoring.conf
│   └── *.env
├── alembic/
├── pyproject.toml
└── README.md
```
