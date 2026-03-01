# Tasks: Server MQTT Ingestor

**Input**: Design documents from `/specs/001-server-mqtt-ingestor/`
**Prerequisites**: plan.md, spec.md, data-model.md, research.md, contracts/ (api-v1.md, mqtt-topics.md), quickstart.md

**Tests**: Обязательны — FR-026 через FR-039 явно требуют интеграционные тесты для каждого типа сообщения, цикла команд, edge cases, reconnect, жизненного цикла домов и схем.

**Organization**: Задачи сгруппированы по user stories для независимой реализации и тестирования каждой истории.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Можно выполнять параллельно (разные файлы, нет зависимостей)
- **[Story]**: К какой user story относится задача (US1, US2, US3)
- Пути файлов указаны от корня репозитория

## Path Conventions

Проект: `server/` (монопроект — FastAPI REST API + MQTT subscriber в едином asyncio event loop)

```text
server/
├── src/cottage_monitoring/   # Исходный код
├── tests/                    # Тесты (unit, integration, contract)
├── deploy/                   # Docker, systemd, nginx, env-файлы
├── alembic/                  # Миграции БД
├── pyproject.toml
└── alembic.ini
```

---

## Phase 0: Server Infrastructure (elion.black-castle.ru)

**Purpose**: Проверка/установка сервисов на elion. Все команды через `ssh elion`.

- [ ] T000 Verify/install infrastructure on elion (ssh elion): PostgreSQL 16 + TimescaleDB extension, Redis 7, Mosquitto MQTT broker, nginx, Docker; create PostgreSQL user `cottage`, databases `cottage_monitoring` + `cottage_monitoring_dev` with TimescaleDB extension; create directories `/opt/cottage-monitoring`, `/etc/cottage-monitoring`, `/var/log/cottage-monitoring/{prod,dev}`; verify all services running via systemctl

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Инициализация проекта, структура каталогов, зависимости, конфигурация деплоя

- [x] T001 Create project directory structure per plan.md and `server/pyproject.toml` with all dependencies (FastAPI, uvicorn, aiomqtt, SQLAlchemy 2.x async, asyncpg, redis[hiredis], alembic, pydantic v2, prometheus-client, structlog; dev: pytest, pytest-asyncio, testcontainers, httpx, ruff, mypy)
- [x] T002 [P] Create Docker infrastructure (для prod/dev deploy + CI/тестов): `server/deploy/Dockerfile` (multi-stage: build + runtime, CMD uvicorn, port via env), `server/deploy/docker-compose.yml` (postgres/timescaledb + redis + mosquitto для локальных тестов), `server/deploy/init-db.sh` (создание обеих БД + расширение TimescaleDB). Тот же Dockerfile используется для сборки образа на elion и для CI.
- [x] T003 [P] Create environment config files `server/deploy/cottage-monitoring.dev.env` (DB: cottage_monitoring_dev, Redis db=1, MQTT_TOPIC_PREFIX=dev/, MQTT_CLIENT_ID=cottage-monitoring-dev, port 8322) and `server/deploy/cottage-monitoring.prod.env` (DB: cottage_monitoring, Redis db=0, MQTT_TOPIC_PREFIX=, MQTT_CLIENT_ID=cottage-monitoring-server, port 8321) per quickstart.md

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Базовая инфраструктура, без которой НИ ОДНА user story не может быть реализована

**⚠️ CRITICAL**: Работа над user stories не может начаться до завершения этой фазы

- [x] T004 Implement Pydantic Settings (all env variables from quickstart.md including MQTT_TOPIC_PREFIX, MQTT_CLIENT_ID) in `server/src/cottage_monitoring/config.py`
- [x] T005 [P] Configure structlog with JSON output + RotatingFileHandler (stdout + file, rotation 50MB × 10, separate MQTT logger) in `server/src/cottage_monitoring/logging_config.py`
- [x] T006 [P] Create SQLAlchemy DeclarativeBase with naming conventions in `server/src/cottage_monitoring/models/base.py`
- [x] T007 [P] Create async engine + async session factory (from config DB_URL) in `server/src/cottage_monitoring/db/session.py`
- [x] T008 [P] Create all ORM models per data-model.md in `server/src/cottage_monitoring/models/`: `house.py` (houses table), `object.py` (objects table with is_timeseries, composite PK house_id+ga), `state.py` (current_state table with JSONB value), `event.py` (events table — TimescaleDB hypertable), `schema_version.py` (schema_versions table, composite PK house_id+schema_hash), `command.py` (commands table, UUID PK, status enum)
- [x] T009 Setup Alembic configuration (`server/alembic.ini`, `server/alembic/env.py` with async support) and create initial migration with all 6 tables + indexes + TimescaleDB hypertable for events in `server/alembic/versions/`
- [x] T010 [P] Create all Pydantic request/response schemas per contracts/api-v1.md in `server/src/cottage_monitoring/schemas/`: `common.py` (ErrorResponse, PaginatedResponse), `house.py`, `object.py`, `state.py`, `event.py` (including TimeseriesPoint), `command.py` (single + batch request)
- [x] T011 [P] Implement MQTT topic parser (strip MQTT_TOPIC_PREFIX, then parse topic string → house_id, message_type enum, params dict) per contracts/mqtt-topics.md in `server/src/cottage_monitoring/mqtt/topic_parser.py`
- [x] T012 [P] Implement aiomqtt client wrapper with TLS support, login/password auth, configurable client_id (MQTT_CLIENT_ID), auto-reconnect with exponential backoff (1s..30s), wildcard subscription `{MQTT_TOPIC_PREFIX}lm/+/v1/#` in `server/src/cottage_monitoring/mqtt/client.py`
- [x] T013 [P] Implement Redis cache wrapper (HSET/HGET/HGETALL per house for current state, connect/disconnect lifecycle) in `server/src/cottage_monitoring/services/redis_cache.py`
- [x] T014 [P] Define all Prometheus metrics per FR-044 (ingestor_messages_total, ingestor_lag_seconds histogram, ingestor_house_status gauge, ingestor_command_latency_seconds histogram, ingestor_command_timeout_total, ingestor_schema_changes_total, ingestor_mqtt_reconnects_total) in `server/src/cottage_monitoring/metrics.py`
- [x] T015 Create FastAPI app with async lifespan (init DB engine, connect Redis, start MQTT subscriber as background task, graceful shutdown) in `server/src/cottage_monitoring/main.py`
- [x] T016 [P] Create API router aggregation in `server/src/cottage_monitoring/api/router.py` and diagnostics endpoints (/health with DB+Redis+MQTT checks, /metrics Prometheus endpoint) in `server/src/cottage_monitoring/api/diagnostics.py`
- [x] T017 [P] Create testcontainers fixtures (PostgreSQL+TimescaleDB, Redis, MQTT broker via Mosquitto) + async DB session fixture + MQTT test client fixture + httpx AsyncClient fixture in `server/tests/conftest.py`

**Checkpoint**: Фундамент готов — можно приступать к реализации user stories

---

## Phase 3: User Story 1 — Приём и хранение телеметрии (Priority: P1) 🎯 MVP

**Goal**: Сервис подключается к MQTT-брокеру, принимает данные (events, state, meta/chunks) от всех домов и сохраняет в БД + Redis-кеш. API позволяет читать сохранённые данные.

**Independent Test**: Подключить тестовый MQTT-клиент, опубликовать сообщения в формате протокола v1 и убедиться, что данные корректно сохранены в БД и Redis.

### Tests for User Story 1 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T018 [P] [US1] Unit tests for topic parser: all 7 message types, MQTT_TOPIC_PREFIX stripping (empty + "dev/"), edge cases (invalid topics, missing segments) in `server/tests/unit/test_topic_parser.py`
- [x] T019 [P] [US1] Unit tests for config validation (required fields, defaults, type coercion) in `server/tests/unit/test_config.py`
- [x] T020 [P] [US1] Integration test: state ingestion — publish retained state/ga/+ via MQTT → verify upsert in current_state table + Redis cache, server_received_ts populated in `server/tests/integration/test_ingestor_state.py`
- [x] T021 [P] [US1] Integration test: events ingestion — publish events via MQTT → verify append in events table, QoS 1 duplicates accepted (no unique constraint), all fields saved in `server/tests/integration/test_ingestor_events.py`
- [x] T022 [P] [US1] Integration test: meta/objects ingestion — publish full meta + chunked meta → verify schema_versions saved, objects table populated, is_timeseries classification correct, chunk assembly works in `server/tests/integration/test_ingestor_meta.py`

### Implementation for User Story 1

- [x] T023 [US1] Implement house_service: auto-register house on first message (create with is_active=true, online_status=unknown), update last_seen on any message in `server/src/cottage_monitoring/services/house_service.py`
- [x] T024 [US1] Implement state_service: upsert current_state (house_id+ga), write-through to Redis HSET, populate server_received_ts, update Prometheus metrics in `server/src/cottage_monitoring/services/state_service.py`
- [x] T025 [P] [US1] Implement event_service: append event to DB (all fields from MQTT payload + server_received_ts + raw_json), update Prometheus metrics in `server/src/cottage_monitoring/services/event_service.py`
- [x] T026 [US1] Implement schema_service: handle full meta (save schema_version, upsert objects with is_timeseries classification per research.md R-001), handle chunked meta (in-memory chunk_buffer, assembly when all chunks received), update Prometheus schema_changes counter in `server/src/cottage_monitoring/services/schema_service.py`
- [x] T027 [US1] Implement ingestor: MQTT message dispatcher — parse topic, validate JSON, route to state_service/event_service/schema_service, call house_service.ensure_house(), handle invalid JSON (log + skip), update ingestor_messages_total metric in `server/src/cottage_monitoring/services/ingestor.py`
- [x] T028 [P] [US1] Implement state API endpoints: GET /api/v1/houses/{house_id}/state (read from Redis, fallback to DB; filter by ga list, tag), GET /api/v1/houses/{house_id}/state/{ga} in `server/src/cottage_monitoring/api/state.py`
- [x] T029 [P] [US1] Implement events API endpoints: GET /api/v1/houses/{house_id}/events (paginated, filter by from/to/ga/type), GET /api/v1/houses/{house_id}/events/timeseries (aggregated data for charts: interval + aggregation function) in `server/src/cottage_monitoring/api/events.py`
- [x] T030 [P] [US1] Implement objects API endpoints: GET /api/v1/houses/{house_id}/objects (filter by tag/q/is_active/is_timeseries), GET /api/v1/houses/{house_id}/objects/{ga} in `server/src/cottage_monitoring/api/objects.py`

**Checkpoint**: US1 полностью функциональна — ingestion pipeline работает, данные сохраняются, API возвращает данные. Можно тестировать независимо.

---

## Phase 4: User Story 2 — Отправка команд и получение подтверждений (Priority: P2)

**Goal**: Сервис формирует команды управления, публикует в MQTT, отслеживает ack от контроллера, реализует retry при таймауте. API позволяет отправлять команды и просматривать их статус.

**Independent Test**: Отправить команду через сервис, симулировать ack от тестового MQTT-клиента и проверить, что статус команды обновлён в БД.

### Tests for User Story 2 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T031 [P] [US2] Integration test: full command lifecycle — send single/batch cmd → MQTT publish, simulate ack ok/error, verify DB status update; timeout scenario (no ack) → retry → timeout status; late ack after timeout; idempotency (duplicate request_id) in `server/tests/integration/test_commands.py`

### Implementation for User Story 2

- [x] T032 [US2] Implement command_service: validate command (house active, GA exists, value matches datatype per data-model.md validation rules), generate UUID request_id, publish to MQTT `{MQTT_TOPIC_PREFIX}lm/{house_id}/v1/cmd`, save to DB with status=sent; handle ack (update ts_ack, status, results); retry scheduler (asyncio background task: check sent commands older than CMD_TIMEOUT_SECONDS, re-publish up to CMD_MAX_RETRIES, set timeout after exhaustion); handle late ack (update status from timeout → ok/error, log late response) in `server/src/cottage_monitoring/services/command_service.py`
- [x] T033 [US2] Extend ingestor: add cmd/ack handler — parse request_id from topic, pass to command_service.handle_ack() in `server/src/cottage_monitoring/services/ingestor.py`
- [x] T034 [US2] Register command retry scheduler as asyncio background task in FastAPI lifespan in `server/src/cottage_monitoring/main.py`
- [x] T035 [US2] Implement commands API endpoints: POST /api/v1/houses/{house_id}/commands (single + batch, validation errors), GET /api/v1/houses/{house_id}/commands (paginated, filter by from/to/status), GET /api/v1/houses/{house_id}/commands/{request_id} in `server/src/cottage_monitoring/api/commands.py`

**Checkpoint**: US1 + US2 работают — данные принимаются, команды отправляются и отслеживаются. Можно тестировать независимо.

---

## Phase 5: User Story 3 — Мониторинг доступности и управление схемой (Priority: P3)

**Goal**: Сервис отслеживает online/offline каждого дома через LWT, ведёт реестр домов с деактивацией/реактивацией, фиксирует изменения схемы объектов (diff), поддерживает RPC-запросы к контроллеру.

**Independent Test**: Симулировать online/offline через тестовый MQTT-клиент (LWT) и проверить обновление статуса дома в БД. Деактивировать дом и убедиться, что сообщения игнорируются.

### Tests for User Story 3 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T036 [P] [US3] Integration test: status/online → house online in DB, LWT offline → house offline in DB, unknown house auto-created in `server/tests/integration/test_ingestor_status.py`
- [x] T037 [P] [US3] Integration test: house lifecycle — auto-create on first message, deactivate (messages ignored + logged as warning), reactivate (messages processed again), data preserved after deactivation in `server/tests/integration/test_house_lifecycle.py`
- [x] T038 [P] [US3] Integration test: schema changes — new schema_hash adds/removes/modifies objects, soft-delete (is_active=false), empty schema (all objects inactive), state/events for inactive objects still accepted in `server/tests/integration/test_schema_changes.py`
- [x] T039 [P] [US3] Integration test: MQTT reconnect — disconnect broker → verify reconnect with exponential backoff, messages processed after reconnect in `server/tests/integration/test_reconnect.py`
- [x] T040 [P] [US3] Integration test: RPC request/response — publish rpc/req, receive rpc/resp, handle chunked responses in `server/tests/integration/test_rpc.py`

### Implementation for User Story 3

- [x] T041 [US3] Extend house_service: handle status/online (update online_status + last_seen), handle LWT offline (update to offline), deactivation/reactivation (PATCH is_active), check is_active before processing messages in `server/src/cottage_monitoring/services/house_service.py`
- [x] T042 [US3] Extend schema_service: diff between old and new schema (added/removed/changed objects), soft-delete removed objects (is_active=false, preserve schema_hash of last active version), handle empty schema, update object attributes on change in `server/src/cottage_monitoring/services/schema_service.py`
- [x] T043 [US3] Extend ingestor: add status/online handler, add rpc/resp handler, add inactive house check (skip + log warning for deactivated houses) in `server/src/cottage_monitoring/services/ingestor.py`
- [x] T044 [US3] Implement rpc_service: generate request_id, publish rpc/req to `{MQTT_TOPIC_PREFIX}lm/{house_id}/v1/rpc/req/{client_id}`, track pending requests, handle rpc/resp (including chunked), timeout for RPC requests in `server/src/cottage_monitoring/services/rpc_service.py`
- [x] T045 [US3] Implement houses API endpoints: GET /api/v1/houses (list with object_count, current_schema_hash), GET /api/v1/houses/{house_id} (detail with schema_versions_count), PATCH /api/v1/houses/{house_id} (is_active toggle) in `server/src/cottage_monitoring/api/houses.py`
- [x] T046 [P] [US3] Implement schemas API endpoints: GET /api/v1/houses/{house_id}/schemas (list versions), GET /api/v1/houses/{house_id}/schemas/{schema_hash} (detail with objects), GET /api/v1/houses/{house_id}/schemas/diff?from=...&to=... in `server/src/cottage_monitoring/api/schemas.py`
- [x] T047 [P] [US3] Implement RPC API endpoints: POST /api/v1/houses/{house_id}/rpc/meta, POST /api/v1/houses/{house_id}/rpc/snapshot in `server/src/cottage_monitoring/api/rpc.py`

**Checkpoint**: Все 3 user stories работают — полный цикл ingestion, команд, мониторинга и управления схемой. Можно тестировать каждую историю независимо.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Контрактные тесты API, edge-case покрытие, деплой, документация

- [x] T048 [P] Contract tests: verify all API endpoints match contracts/api-v1.md (request/response schemas, status codes, pagination, error format) in `server/tests/contract/test_api_contracts.py`
- [x] T049 [P] Unit tests for command validators (all datatypes: bool, percentage, uint16, int16, float16, float32, string; boundary values, invalid types) in `server/tests/unit/test_validators.py`
- [x] T050 [P] Integration tests for edge cases (FR-029): invalid JSON in MQTT messages, incomplete meta chunks + RPC fallback, duplicate meta with same schema_hash, message for GA not in schema in `server/tests/integration/test_edge_cases.py`
- [x] T051 [P] Create deploy artifacts for elion: systemd unit files that run Docker containers (`server/deploy/cottage-monitoring.service` — `docker run --network=host --env-file ... cottage-monitoring:latest` prod port 8321, `server/deploy/cottage-monitoring-dev.service` — аналогично, dev port 8322), nginx reverse proxy config (`server/deploy/nginx/cottage-monitoring.conf` with monitoring.black-castle.ru + monitoring-dev.black-castle.ru) per research.md R-004, R-006
- [x] T052 Create `server/README.md` with project overview, architecture, elion server info, SSH tunnel instructions, quickstart commands, API documentation link
- [ ] T053 Validate quickstart.md scenarios end-to-end on elion (ssh elion): docker build, run migrations via `docker run --rm`, start systemd service (docker container), health check, publish test event via mosquitto_pub to dev/ topic, verify API response on port 8322, check `docker logs` and journalctl

---

## Dependencies & Execution Order

### Phase Dependencies

- **Infrastructure (Phase 0)**: Нет зависимостей — проверка/установка сервисов на elion
- **Setup (Phase 1)**: Зависит от Phase 0 (БД и сервисы должны быть готовы)
- **Foundational (Phase 2)**: Зависит от Phase 1 — **БЛОКИРУЕТ** все user stories
- **User Stories (Phase 3-5)**: Все зависят от завершения Phase 2
  - User stories можно реализовывать параллельно (если есть ресурсы)
  - Или последовательно в порядке приоритета (P1 → P2 → P3)
- **Polish (Phase 6)**: Зависит от завершения всех user stories

### User Story Dependencies

- **US1 (P1)**: Может начаться после Phase 2 — нет зависимостей от других stories
- **US2 (P2)**: Может начаться после Phase 2 — зависит от house_service из US1 (auto-register), но может использовать foundational models напрямую. Рекомендуется после US1.
- **US3 (P3)**: Может начаться после Phase 2 — расширяет house_service и schema_service из US1. Рекомендуется после US1.

### Within Phase 2 (Internal Order)

```
T004 (config) ──────────────────────────────────┐
   │                                             │
   ├─→ T005 [P] (logging)                       │
   ├─→ T006 [P] (base.py)                       │
   ├─→ T007 [P] (session.py)                    │
   │       │                                     │
   │       └─→ T008 (ORM models, needs T006) ───┤
   │               │                             │
   │               └─→ T009 (Alembic, needs T007+T008)
   │                                             │
   ├─→ T010 [P] (Pydantic schemas)              │
   ├─→ T011 [P] (topic parser)                  │
   ├─→ T012 [P] (MQTT client)                   │
   ├─→ T013 [P] (Redis cache)                   │
   ├─→ T014 [P] (Prometheus metrics)            │
   │                                             │
   └─→ T015 (main.py, needs T004-T014) ─────────┤
           │                                     │
           ├─→ T016 [P] (API router + diagnostics)
           └─→ T017 [P] (test conftest)
```

### Within Each User Story

1. Тесты MUST быть написаны и FAIL до начала реализации
2. Модели/сервисы перед API endpoints
3. Базовая реализация перед интеграцией
4. Checkpoint после завершения каждой story

### Parallel Opportunities

- **Phase 1**: T002 и T003 параллельно (после T001)
- **Phase 2**: T005, T006, T007, T010-T014 все параллельно (после T004)
- **Phase 3 (US1)**: Все тесты (T018-T022) параллельно; API endpoints (T028-T030) параллельно
- **Phase 4 (US2)**: Тест T031 параллельно с другими фазами
- **Phase 5 (US3)**: Все тесты (T036-T040) параллельно; T046, T047 параллельно
- **Phase 6**: T048-T051 все параллельно

---

## Parallel Example: User Story 1

```bash
# Все тесты US1 параллельно (должны FAIL):
Task: "Unit tests for topic parser in server/tests/unit/test_topic_parser.py"
Task: "Unit tests for config in server/tests/unit/test_config.py"
Task: "Integration test state in server/tests/integration/test_ingestor_state.py"
Task: "Integration test events in server/tests/integration/test_ingestor_events.py"
Task: "Integration test meta in server/tests/integration/test_ingestor_meta.py"

# Затем сервисы (частично параллельно):
Task: "house_service in server/src/cottage_monitoring/services/house_service.py"
Task: "state_service in server/src/cottage_monitoring/services/state_service.py"
Task: "event_service in server/src/cottage_monitoring/services/event_service.py"  # [P]
Task: "schema_service in server/src/cottage_monitoring/services/schema_service.py"

# Затем ingestor (зависит от всех сервисов):
Task: "ingestor in server/src/cottage_monitoring/services/ingestor.py"

# Все API endpoints параллельно:
Task: "State API in server/src/cottage_monitoring/api/state.py"
Task: "Events API in server/src/cottage_monitoring/api/events.py"
Task: "Objects API in server/src/cottage_monitoring/api/objects.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — блокирует все stories)
3. Complete Phase 3: User Story 1 (ingestion pipeline + read API)
4. **STOP and VALIDATE**: Тестировать US1 независимо — MQTT → DB → API
5. Deploy/demo если готово

### Incremental Delivery

1. Setup + Foundational → Фундамент готов
2. Add US1 → Тест → Deploy (MVP! Read-only мониторинг работает)
3. Add US2 → Тест → Deploy (Добавлено управление командами)
4. Add US3 → Тест → Deploy (Полная система: мониторинг + команды + lifecycle)
5. Polish → Контрактные тесты, edge cases, deploy artifacts

### Suggested MVP Scope

**Только US1** — приём и хранение телеметрии. Это даёт:
- Работающий ingestion pipeline (MQTT → DB + Redis)
- Read API для state, events, objects
- Prometheus метрики для Grafana
- Достаточно для начала мониторинга реальных домов

---

## Notes

- [P] tasks = разные файлы, нет зависимостей — можно выполнять параллельно
- [Story] label привязывает задачу к конкретной user story для трассировки
- Каждая user story должна быть независимо завершаемой и тестируемой
- Тесты MUST быть написаны и FAIL до реализации
- Commit после каждой задачи или логической группы
- Остановка на любом checkpoint для валидации story
- Избегать: нечёткие задачи, конфликты в одном файле, кросс-story зависимости
