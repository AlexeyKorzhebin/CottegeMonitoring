# Implementation Checklist: Server MQTT Ingestor

**Purpose**: Трекинг реализации всех функциональных требований, инфраструктуры и тестов
**Created**: 2026-03-01
**Feature**: [spec.md](../spec.md) | [plan.md](../plan.md)

---

## 1. Инфраструктура проекта

- [ ] CHK-I01 Создать `server/pyproject.toml` с зависимостями (FastAPI, aiomqtt, SQLAlchemy 2.x async, asyncpg, redis, alembic, pydantic v2, prometheus-client, structlog, uvicorn)
- [ ] CHK-I02 Создать структуру пакета `server/src/cottage_monitoring/` с `__init__.py`
- [ ] CHK-I03 Настроить `server/alembic.ini` и `server/alembic/env.py` (async engine)
- [ ] CHK-I04 Создать первую миграцию Alembic: все таблицы из data-model.md (houses, objects, current_state, events, schema_versions, commands)
- [ ] CHK-I05 Создать TimescaleDB hypertable для таблицы events в миграции
- [ ] CHK-I06 Создать все индексы из data-model.md (events по house_id+ts, house_id+ga+ts; commands по house_id+ts_sent, status)
- [ ] CHK-I07 Настроить `config.py` — Pydantic Settings с env-переменными из quickstart.md
- [ ] CHK-I08 Настроить `logging_config.py` — structlog + RotatingFileHandler (JSON, 50MB × 10, раздельные app.log и mqtt.log)
- [ ] CHK-I09 Настроить `db/session.py` — async session factory (SQLAlchemy + asyncpg)
- [ ] CHK-I10 Создать `main.py` — FastAPI app с lifespan (startup: MQTT + Redis + DB; shutdown: graceful)

## 2. MQTT слой (Протокол обмена)

- [ ] CHK-M01 **FR-001** `mqtt/client.py` — подписка на `lm/+/v1/#`
- [ ] CHK-M02 **FR-002** `mqtt/topic_parser.py` — парсинг `lm/<house_id>/v1/<subtopic>` → (house_id, message_type, params)
- [ ] CHK-M03 **FR-003** `services/ingestor.py` — dispatcher для всех типов сообщений: events, state/ga/*, meta/objects, meta/objects/chunk/*, status/online, cmd/ack/*, rpc/resp/*/*
- [ ] CHK-M04 **FR-004** Валидация JSON во входящих сообщениях; невалидные → лог ошибки, skip
- [ ] CHK-M05 **FR-024** Auto-reconnect к MQTT-брокеру с exponential backoff (1s → 30s max)
- [ ] CHK-M06 **FR-025** Внутренний буфер/очередь для burst-нагрузки (asyncio.Queue)
- [ ] CHK-M07 **FR-046** TLS подключение к MQTT-брокеру (опционально через конфиг)
- [ ] CHK-M08 **FR-047** Аутентификация логин/пароль из env-переменных; credentials НЕ в коде

## 3. Хранение состояния (State)

- [ ] CHK-S01 **FR-005** `models/state.py` — ORM-модель current_state (PK: house_id + ga)
- [ ] CHK-S02 **FR-006** `services/state_service.py` — upsert при получении state/ga/* (house_id, ga, ts, value, datatype)
- [ ] CHK-S03 **FR-007** Сохранение `server_received_ts` при каждом upsert state
- [ ] CHK-S04 `services/redis_cache.py` — HSET `state:{house_id}` при каждом upsert state (зеркало PostgreSQL)
- [ ] CHK-S05 Redis fallback: при cache miss → чтение из PostgreSQL

## 4. Хранение событий (Events)

- [ ] CHK-E01 **FR-008** `models/event.py` — ORM-модель events (house_id, ts, seq, type, ga, id, name, datatype, value, raw_json)
- [ ] CHK-E02 **FR-008** `services/event_service.py` — INSERT event при получении events
- [ ] CHK-E03 **FR-009** Индексы: (house_id, ts DESC) и (house_id, ga, ts DESC)
- [ ] CHK-E04 **FR-048** Бессрочное хранение — НЕ реализовывать ротацию/удаление
- [ ] CHK-E05 **FR-049** Append-only — НЕ устанавливать unique constraint; дубликаты QoS 1 допустимы

## 5. Схема объектов (Meta)

- [ ] CHK-O01 **FR-010** `models/schema_version.py` — ORM-модель schema_versions (PK: house_id + schema_hash)
- [ ] CHK-O02 **FR-011** `services/schema_service.py` — сборка чанков по (schema_hash, chunk_total); формирование полной схемы когда все чанки получены
- [ ] CHK-O03 **FR-012** `models/object.py` — ORM-модель objects; обновление таблицы при новой полной схеме (house_id, ga, object_id, name, datatype, units, tags, comment, schema_hash)
- [ ] CHK-O04 **FR-031** Diff объектов при новой схеме: определение добавленных, удалённых, изменённых
- [ ] CHK-O05 **FR-032** Soft delete: отсутствующие объекты → `is_active=false`; физическое удаление запрещено
- [ ] CHK-O06 **FR-033** State/events для неактивных или незарегистрированных объектов → принимать и сохранять без ошибки
- [ ] CHK-O07 Маркировка `is_timeseries` при обновлении объектов (по тегам/datatype из research.md R-001)
- [ ] CHK-O08 Chunk buffer (in-memory dict) с таймаутом на неполные чанки

## 6. Дома и статус

- [ ] CHK-H01 **FR-013** `models/house.py` — ORM-модель houses (house_id, created_at, last_seen, online_status, is_active)
- [ ] CHK-H02 **FR-014** `services/house_service.py` — обновление online_status=online + last_seen при получении status=online
- [ ] CHK-H03 **FR-015** Обновление online_status=offline при LWT
- [ ] CHK-H04 **FR-016** Автосоздание дома при первом сообщении с неизвестным house_id (is_active=true)
- [ ] CHK-H05 **FR-035** Деактивация дома (is_active=false); все данные сохраняются
- [ ] CHK-H06 **FR-036** Для деактивированного дома — skip обработки MQTT + лог WARNING
- [ ] CHK-H07 **FR-037** Реактивация дома (is_active=true); возобновление обработки
- [ ] CHK-H08 **FR-038** Автоматическое удаление/деактивация по таймауту НЕ реализуется

## 7. Команды

- [ ] CHK-C01 **FR-017** `services/command_service.py` — приём запроса (house_id, ga, value) или batch (house_id, items[{ga, value}])
- [ ] CHK-C02 **FR-018** Генерация UUID request_id
- [ ] CHK-C03 **FR-019** Публикация в `lm/<house_id>/v1/cmd` в JSON-формате протокола
- [ ] CHK-C04 **FR-020** Сохранение команды в БД: house_id, request_id, ts_sent, payload
- [ ] CHK-C05 **FR-021** Обработка ack из cmd/ack/* → обновление ts_ack, status, results
- [ ] CHK-C06 **FR-022** Идемпотентность: повторная cmd с тем же request_id НЕ создаёт новую запись
- [ ] CHK-C07 **FR-040** Retry: повторная публикация cmd через 60с если нет ack (max 2 retry)
- [ ] CHK-C08 **FR-041** Статус timeout после исчерпания retry
- [ ] CHK-C09 **FR-042** Late ack: обновление статуса из ack после timeout + лог
- [ ] CHK-C10 Валидация команд (Principle VI): проверка house is_active, ga существует, value соответствует datatype, тег control (warning для status)
- [ ] CHK-C11 Retry scheduler как asyncio background task

## 8. RPC

- [ ] CHK-R01 **FR-023** `services/rpc_service.py` — публикация rpc/req/<client_id> (method: snapshot/meta)
- [ ] CHK-R02 **FR-023** Обработка rpc/resp/<client_id>/<request_id>

## 9. REST API (FastAPI)

- [ ] CHK-A01 `api/router.py` — агрегация всех роутеров
- [ ] CHK-A02 `api/houses.py` — GET /houses, GET /houses/{house_id}, PATCH /houses/{house_id}
- [ ] CHK-A03 `api/objects.py` — GET /houses/{house_id}/objects, GET /houses/{house_id}/objects/{ga}; фильтры по tag, name, is_active, is_timeseries
- [ ] CHK-A04 `api/state.py` — GET /houses/{house_id}/state (из Redis), GET /houses/{house_id}/state/{ga}; фильтры по ga, tag
- [ ] CHK-A05 `api/events.py` — GET /houses/{house_id}/events (из TimescaleDB); фильтры по from/to, ga, type
- [ ] CHK-A06 `api/events.py` — GET /houses/{house_id}/events/timeseries — агрегации для графиков (avg, min, max, last, sum, count) с интервалами
- [ ] CHK-A07 `api/commands.py` — POST /houses/{house_id}/commands (single + batch), GET /houses/{house_id}/commands, GET /houses/{house_id}/commands/{request_id}
- [ ] CHK-A08 `api/diagnostics.py` — GET /health (mqtt + db + redis статус), GET /metrics (Prometheus)
- [ ] CHK-A09 `api/houses.py` — POST /houses/{house_id}/rpc/meta, POST /houses/{house_id}/rpc/snapshot
- [ ] CHK-A10 Schemas diff: GET /houses/{house_id}/schemas, GET /houses/{house_id}/schemas/{hash}, GET /houses/{house_id}/schemas/diff?from=&to=
- [ ] CHK-A11 Pydantic v2 schemas для всех request/response моделей (`schemas/`)
- [ ] CHK-A12 Единый формат ошибок: `{"error": {"code", "message", "details"}}`
- [ ] CHK-A13 Пагинация: limit/offset для списочных endpoints

## 10. Наблюдаемость

- [ ] CHK-L01 **FR-043** Структурированные логи (JSON): ts, level, house_id, message_type, message
- [ ] CHK-L02 **FR-044** Prometheus метрика: `ingestor_messages_total{house_id, message_type}`
- [ ] CHK-L03 **FR-044** Prometheus метрика: `ingestor_lag_seconds{house_id}` (histogram)
- [ ] CHK-L04 **FR-044** Prometheus метрика: `ingestor_house_status{house_id}` (gauge)
- [ ] CHK-L05 **FR-044** Prometheus метрика: `ingestor_command_latency_seconds{house_id}` (histogram)
- [ ] CHK-L06 **FR-044** Prometheus метрика: `ingestor_command_timeout_total{house_id}`
- [ ] CHK-L07 **FR-044** Prometheus метрика: `ingestor_schema_changes_total{house_id}`
- [ ] CHK-L08 **FR-044** Prometheus метрика: `ingestor_mqtt_reconnects_total`
- [ ] CHK-L09 Ротация логов: RotatingFileHandler (50MB × 10 файлов)
- [ ] CHK-L10 Раздельные логгеры: app.log (основной), mqtt.log (MQTT-специфичный)

## 11. Деплой

### Базы данных

- [ ] CHK-D01 `deploy/init-db.sh` — скрипт создания обеих БД: `cottage_monitoring` (prod) + `cottage_monitoring_dev` (dev), TimescaleDB extension в обеих
- [ ] CHK-D02 Alembic: миграции применяются к каждой базе отдельно через `DB_URL`
- [ ] CHK-D03 Redis: dev использует DB 1 (`redis://…/1`), prod использует DB 0 (`redis://…/0`)

### Docker

- [ ] CHK-D04 `deploy/Dockerfile` — multi-stage build, Python 3.12-slim
- [ ] CHK-D05 `deploy/docker-compose.yml` — app + postgres (timescaledb, обе базы) + redis + mosquitto (dev)
- [ ] CHK-D06 `deploy/docker-compose.prod.yml` — production overrides (без mosquitto, внешний broker, prod DB)
- [ ] CHK-D07 `deploy/cottage-monitoring.dev.env` — dev env (cottage_monitoring_dev, DEBUG, порт 8322)
- [ ] CHK-D08 `deploy/cottage-monitoring.prod.env` — prod env (cottage_monitoring, INFO, порт 8321, TLS)

### Systemd

- [ ] CHK-D09 `deploy/cottage-monitoring.service` — systemd unit production (порт 8321, prod.env)
- [ ] CHK-D10 `deploy/cottage-monitoring-dev.service` — systemd unit dev (порт 8322, dev.env)
- [ ] CHK-D11 Инструкция создания пользователя `cottage-monitoring` и директорий `/opt/cottage-monitoring`, `/var/log/cottage-monitoring`

### Nginx

- [ ] CHK-D12 `deploy/nginx/cottage-monitoring.conf` — два upstream: prod (:8321) + dev (:8322)
- [ ] CHK-D13 Production server block: /api/, /metrics (restricted), /health, /docs, /openapi.json
- [ ] CHK-D14 Dev server block: проксирование всех запросов на dev-инстанс
- [ ] CHK-D15 Ограничение доступа к /metrics (allow 127.0.0.1, allow 10.0.0.0/8, deny all)

## 12. Тесты

### Unit-тесты

- [ ] CHK-T01 `tests/unit/test_topic_parser.py` — парсинг всех типов топиков, edge cases
- [ ] CHK-T02 `tests/unit/test_config.py` — загрузка конфигурации из env
- [ ] CHK-T03 `tests/unit/test_validators.py` — валидация команд по datatype (bool, percent, int16, float, string)

### Integration-тесты

- [ ] CHK-T04 **FR-026** `test_ingestor_state.py` — полный цикл: MQTT state → PostgreSQL + Redis
- [ ] CHK-T05 **FR-026** `test_ingestor_events.py` — полный цикл: MQTT events → TimescaleDB
- [ ] CHK-T06 **FR-026** `test_ingestor_meta.py` — meta/objects полная + чанки → schema_versions + objects
- [ ] CHK-T07 **FR-026** `test_ingestor_status.py` — online/offline (LWT) → houses
- [ ] CHK-T08 **FR-027** Тест полного цикла: publish MQTT → ingestor → проверка записи в БД
- [ ] CHK-T09 **FR-028** `test_commands.py` — цикл команд: формирование → MQTT pub → sim ack → update БД
- [ ] CHK-T10 **FR-029** Edge cases: невалидный JSON, дубликаты QoS 1, неполные чанки, неизвестный house_id
- [ ] CHK-T11 **FR-030** `test_reconnect.py` — reconnect к MQTT после обрыва
- [ ] CHK-T12 **FR-034** `test_schema_changes.py` — add/remove/change объектов, state для неактивных, пустая схема
- [ ] CHK-T13 **FR-039** `test_house_lifecycle.py` — автосоздание, деактивация (skip), реактивация, сохранность данных
- [ ] CHK-T14 `test_commands.py` — retry + timeout + late ack
- [ ] CHK-T15 `test_rpc.py` — RPC meta/snapshot publish + response handling

### Contract-тесты API

- [ ] CHK-T16 `test_api_contracts.py` — все endpoints из contracts/api-v1.md возвращают корректные HTTP-коды и schema
- [ ] CHK-T17 Тест ошибок API: 400 validation, 404 not found

### Fixtures

- [ ] CHK-T18 `tests/conftest.py` — testcontainers: PostgreSQL + TimescaleDB, Redis, Mosquitto
- [ ] CHK-T19 Фикстуры для тестовых данных: house, objects, events, commands

## 13. Документация

- [ ] CHK-DOC1 `server/README.md` — описание проекта, quickstart, архитектура
- [ ] CHK-DOC2 Автогенерируемый OpenAPI (Swagger UI) на /docs

## Summary

| Категория | Всего | Покрытие FR |
|-----------|-------|-------------|
| Инфраструктура | 10 | — |
| MQTT слой | 8 | FR-001..004, FR-024..025, FR-046..047 |
| State | 5 | FR-005..007 |
| Events | 5 | FR-008..009, FR-048..049 |
| Meta/Objects | 8 | FR-010..012, FR-031..033 |
| Houses | 8 | FR-013..016, FR-035..038 |
| Commands | 11 | FR-017..022, FR-040..042 |
| RPC | 2 | FR-023 |
| REST API | 13 | FR-044 (partial) |
| Наблюдаемость | 10 | FR-043..044 |
| Деплой | 15 | — |
| Тесты | 19 | FR-026..030, FR-034, FR-039 |
| Документация | 2 | FR-045 (out of scope noted) |
| **ИТОГО** | **116** | **49 FR покрыты** |
