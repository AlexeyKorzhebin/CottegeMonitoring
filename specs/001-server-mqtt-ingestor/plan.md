# Implementation Plan: Server MQTT Ingestor

**Branch**: `001-server-mqtt-ingestor` | **Date**: 2026-03-01 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-server-mqtt-ingestor/spec.md`

## Summary

Серверный сервис на Python (FastAPI + aiomqtt) для приёма телеметрии
от домов через MQTT, хранения в PostgreSQL/TimescaleDB, кеширования
актуального среза в Redis и предоставления REST API для внешних систем
и MCP-серверов. Сервис работает как Docker-контейнер, управляемый systemd,
на `elion.black-castle.ru` за nginx reverse proxy на порту **8321**.

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: FastAPI, uvicorn, aiomqtt (asyncio MQTT client), SQLAlchemy 2.x (async), asyncpg, redis[hiredis], alembic, pydantic v2, prometheus-client, structlog
**Server**: `elion.black-castle.ru` (SSH: `ssh elion`, sudo доступен)
**Storage**: PostgreSQL 16 + TimescaleDB (events hypertable), Redis 7 (current state cache) — всё на elion
**MQTT Broker**: Mosquitto на elion (localhost:1883); dev/prod изоляция через `MQTT_TOPIC_PREFIX`
**Testing**: pytest, pytest-asyncio, testcontainers-python (Postgres + Redis + MQTT), httpx (API tests)
**Target Platform**: Linux (Ubuntu на elion.black-castle.ru)
**Project Type**: web-service (FastAPI REST API + MQTT subscriber daemon)
**Performance Goals**: 10 домов одновременно, обработка state <1с, команда <2с до контроллера
**Constraints**: <200ms p95 API response (cached state), <5с lag ingestion, порт 8321 (за nginx на elion)
**Scale/Scope**: 10 домов, ~150 объектов на дом, ~1500 объектов суммарно
**Dev Access**: SSH tunnel (`ssh -L 5432:localhost:5432 -L 6379:localhost:6379 -L 1883:localhost:1883 elion -N`)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Принцип | Статус | Обоснование |
|---------|--------|-------------|
| I. Двухуровневая архитектура | ✅ PASS | Сервис — облачная часть. Не зависит от контроллера. Единственная связь — MQTT. |
| II. MQTT как единая шина | ✅ PASS | Все данные приходят/уходят через MQTT. Прямых соединений с контроллером нет. |
| III. KNX-стандартизация | ✅ PASS | Сервер принимает нормализованные объекты через MQTT, не работает с KNX напрямую. |
| IV. API-First | ✅ PASS | FastAPI предоставляет REST API для MCP, UI, интеграций. Redis обеспечивает real-time доступ к состоянию. |
| V. Раздельное тестирование | ✅ PASS | Серверные тесты полностью независимы от Lua/контроллера. pytest + testcontainers. |
| VI. Безопасность управления | ✅ PASS | Команды валидируются по типу данных и допустимому диапазону перед отправкой. |
| Technology Stack | ⚠️ NOTE | Redis (кеш) — дополнение к стеку. Не заменяет PostgreSQL как primary store. FastAPI — Python framework, вписывается в "Python Daemon". **Рекомендуется внести Redis в конституцию как PATCH (1.0.1).** |

## Project Structure

### Documentation (this feature)

```text
specs/001-server-mqtt-ingestor/
├── plan.md              # Этот файл
├── research.md          # Phase 0: исследование и решения
├── data-model.md        # Phase 1: модель данных + классификация объектов
├── quickstart.md        # Phase 1: быстрый старт
├── contracts/           # Phase 1: API контракты
│   ├── api-v1.md        # REST API endpoints
│   └── mqtt-topics.md   # MQTT topic contracts
└── tasks.md             # Phase 2 (/speckit.tasks)
```

### Source Code (repository root)

```text
server/
├── src/
│   └── cottage_monitoring/
│       ├── __init__.py
│       ├── main.py                  # FastAPI app + lifespan (MQTT startup)
│       ├── config.py                # Pydantic Settings (env/file)
│       ├── logging_config.py        # structlog + file rotation
│       ├── metrics.py               # Prometheus metrics definitions
│       ├── models/                  # SQLAlchemy ORM models
│       │   ├── __init__.py
│       │   ├── base.py              # DeclarativeBase
│       │   ├── house.py
│       │   ├── object.py
│       │   ├── state.py
│       │   ├── event.py
│       │   ├── schema_version.py
│       │   └── command.py
│       ├── schemas/                 # Pydantic request/response schemas
│       │   ├── __init__.py
│       │   ├── house.py
│       │   ├── object.py
│       │   ├── state.py
│       │   ├── event.py
│       │   ├── command.py
│       │   └── common.py
│       ├── services/                # Business logic
│       │   ├── __init__.py
│       │   ├── ingestor.py          # MQTT message dispatcher
│       │   ├── state_service.py     # State upsert + Redis cache
│       │   ├── event_service.py     # Event append
│       │   ├── schema_service.py    # Meta/chunk assembly, object diff
│       │   ├── command_service.py   # Cmd publish + ack tracking + retry
│       │   ├── house_service.py     # House registry + online/offline
│       │   ├── rpc_service.py       # RPC req/resp
│       │   └── redis_cache.py       # Redis wrapper for current state
│       ├── api/                     # FastAPI routers
│       │   ├── __init__.py
│       │   ├── router.py            # Main router aggregation
│       │   ├── houses.py
│       │   ├── objects.py
│       │   ├── state.py
│       │   ├── events.py
│       │   ├── commands.py
│       │   └── diagnostics.py       # /health, /metrics
│       ├── mqtt/                    # MQTT client layer
│       │   ├── __init__.py
│       │   ├── client.py            # aiomqtt wrapper + reconnect
│       │   └── topic_parser.py      # Topic → (house_id, message_type, params)
│       └── db/                      # Database utilities
│           ├── __init__.py
│           └── session.py           # async session factory
├── tests/
│   ├── conftest.py                  # testcontainers fixtures
│   ├── unit/
│   │   ├── test_topic_parser.py
│   │   ├── test_config.py
│   │   └── test_validators.py
│   ├── integration/
│   │   ├── test_ingestor_state.py
│   │   ├── test_ingestor_events.py
│   │   ├── test_ingestor_meta.py
│   │   ├── test_ingestor_status.py
│   │   ├── test_commands.py
│   │   ├── test_rpc.py
│   │   ├── test_reconnect.py
│   │   ├── test_house_lifecycle.py
│   │   └── test_schema_changes.py
│   └── contract/
│       └── test_api_contracts.py
├── deploy/
│   ├── Dockerfile
│   ├── docker-compose.yml           # postgres + redis + mosquitto (для тестов/CI)
│   ├── cottage-monitoring.service   # systemd: docker run prod (порт 8321)
│   ├── cottage-monitoring-dev.service # systemd: docker run dev (порт 8322)
│   ├── cottage-monitoring.dev.env   # env: dev (cottage_monitoring_dev, DEBUG)
│   ├── cottage-monitoring.prod.env  # env: production (cottage_monitoring, INFO)
│   ├── init-db.sh                   # скрипт создания обеих БД + TimescaleDB
│   └── nginx/
│       └── cottage-monitoring.conf  # nginx: prod (:8321) + dev (:8322)
├── alembic/
│   ├── env.py
│   └── versions/
├── alembic.ini
├── pyproject.toml
└── README.md
```

**Structure Decision**: Монопроект (Single project) — один Python-сервис объединяет
MQTT ingestor и FastAPI API в едином asyncio event loop. Деплой на elion — Docker-
контейнеры (prod + dev), управляемые systemd (`--network=host` для доступа к host
PostgreSQL/Redis/MQTT). Локальная разработка через SSH tunnel к сервисам на elion.
Docker Compose — для интеграционных тестов (testcontainers) и CI.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Redis (не в конституции) | Кеш актуального среза для API <200ms; Principle IV требует real-time доступ | Прямой запрос к PostgreSQL даёт >500ms при 1500 объектах; Redis — read-through cache, не primary store |
| FastAPI (расширение "Python Daemon") | API-First (Principle IV); REST endpoints для MCP, UI, интеграций | Чистый daemon без API не удовлетворяет Principle IV |
