# Бизнес-спецификация и системный анализ
## Проект: мониторинг домов через LogicMachine → MQTT → сервер мониторинга
Версия: 1.0 (v1 протокола)  
Статус: согласовано с подходом **events + retained state + meta + cmd + RPC + LWT**

---

## 1) Бизнес-контекст

### 1.1 Цель продукта
Единая система мониторинга для нескольких домов/объектов автоматизации, где LogicMachine выступает “полевым шлюзом”, а сервер мониторинга собирает телеметрию/состояния, хранит историю, отображает в UI, поднимает алерты и отправляет команды.

### 1.2 Основные ценности
- **Оперативная видимость**: “что сейчас происходит в доме” (retained state + online/offline).
- **История и аналитика**: изменения, тренды, расследования (event log).
- **Управляемость**: удалённые команды и подтверждения (cmd + ack).
- **Масштабирование**: много домов в одном мониторинге (house_id namespace).
- **Самоописание**: схема объектов и её изменения (meta + schema_hash).

### 1.3 Заинтересованные стороны (персоны)
- **Оператор/диспетчер**: следит за алертами, видит статусы, быстро диагностирует.
- **Инженер/интегратор**: подключает новый дом, настраивает фильтры/теги, отлаживает.
- **Серверный разработчик**: пишет ingestion pipeline, хранение, алерты, API.
- **Администратор инфраструктуры**: MQTT брокер, TLS, доступы, наблюдаемость.

---

## 2) Область системы (Scope)

### 2.1 В scope
**Клиент (LogicMachine App):**
- Публикация `events` (stream), `state/*` (retained), `meta/objects` (retained, чанки).
- LWT online/offline.
- Приём `cmd` (GA/value) и выполнение через `grp.update()` (виртуальная шина) + `cmd/ack`.
- RPC: запросы на `snapshot`/`meta` по `rpc/req/*` и ответ по `rpc/resp/*`.

**Сервер мониторинга:**
- Подписка на топики домов.
- Нормализация, валидация контрактов, хранение state/history/meta.
- UI/АПИ для просмотра состояния, истории, мета-схемы и алертов.
- Генерация команд (cmd) и приём ack.
- Управление схемой (schema_hash) и обнаружение новых объектов.

### 2.2 Не в scope (на данном этапе)
- Автоматическая конфигурация LM “с нуля” (provisioning через отдельный канал).
- Сложная RBAC-модель по пользователям (можно добавить позже).
- Синхронизация времени (предполагаем корректный NTP на стороне LM/сервера).

---

## 3) Нефункциональные требования (NFR)

### 3.1 Надёжность
- Клиент устойчив к падению брокера: очередь + reconnect + отсутствие потери работоспособности.
- Сервер устойчив к burst-нагрузке: ingestion pipeline с буфером/очередью.

### 3.2 Производительность
- Клиент не должен “зажимать” CPU: короткий цикл + частый `mqtt.loop()` + минимальная работа в handler.
- Серверная обработка событий — потоковая, без тяжёлых блокировок.

### 3.3 Масштабирование
- Много домов и контроллеров: все топики имеют префикс `cm/<house_id>/<device_id>/v1/…`
- В одном доме может быть один или несколько контроллеров LogicMachine (device). Контроллер управляет только одним домом или его частью.
- Возможность горизонтального масштабирования ingestion (consumer group по MQTT/bridge).

### 3.4 Безопасность
- MQTT: TLS по возможности, авторизация по логинам/ACL на топики домов.
- Команды: доверяем серверу (валидация на сервере), но сохраняем технический `ack`.
- Логи и meta могут содержать чувствительную информацию → доступ ограничен.

---

## 4) Системный анализ и архитектура

### 4.1 Компоненты (логическая архитектура)

**Client side (LogicMachine):**
1) **Web Configurator (Apps UI)**  
   Настройка broker/house_id/фильтров/очереди/debug.
2) **Daemon exporter**  
   - localbus listener  
   - MQTT publisher/subscriber  
   - queue + dedup  
   - meta/snapshot producer  
   - cmd executor + ack

**Server side:**
1) **MQTT Broker** (Mosquitto/EMQX/HiveMQ и т.п.)  
2) **Ingestor** (подписчик/консьюмер)  
   - читает `events`, `state`, `meta`, `status`, `ack`  
   - пишет в хранилища
3) **State Store** (KV/DB)  
   - актуальное состояние по объекту
4) **History Store** (TSDB/SQL/Timeseries)  
   - история событий/изменений
5) **Schema/Meta Registry**  
   - хранит meta/objects, schema_hash, диффы/версии
6) **Alert Engine**  
   - правила, пороги, анемометр “offline”
7) **API + UI**  
   - UI для операторов/инженеров  
   - API для интеграций
8) **Command Service**  
   - публикует `cmd`  
   - принимает `ack`  
   - связывает команды с UI/логикой

---

## 5) Протокол и контракты (v1)

### 5.1 Namespace
`cm/<house_id>/<device_id>/v1/`

`house_id` уникален в системе мониторинга. `device_id` уникален в рамках дома и идентифицирует конкретный контроллер LogicMachine.

В одном доме может быть один или несколько контроллеров (device). Каждый контроллер управляет только одним домом или его частью. Отношение: House 1:N Device, Device N:1 House.

### 5.2 Topic Tree (контракт)

Все топики относительно namespace `cm/<house_id>/<device_id>/v1/`:

| Назначение | Topic | QoS | Retain | Producer | Consumer |
|---|---|---:|---:|---|---|
| Журнал событий | `events` | 0/1 | no | LM | Server |
| Последнее состояние | `state/ga/<ga>` | 1 | yes | LM | Server |
| Схема объектов | `meta/objects` (+chunk) | 1 | yes | LM | Server |
| Online/offline | `status/online` | 1 | yes | LM (LWT) | Server |
| Команды | `cmd` | 1 | no | Server | LM |
| Ack команд | `cmd/ack/<request_id>` | 0/1 | no | LM | Server |
| RPC req | `rpc/req/<client_id>` | 0/1 | no | Server | LM |
| RPC resp | `rpc/resp/<client_id>/<request_id>` | 0/1 | no | LM | Server |

---

## 6) Модели сообщений (JSON)

### 6.1 Общие поля
- `ts` (unix time seconds) — когда сформировано сообщение.
- `house_id` и `device_id` не передаём в payload (они в топике), но сервер извлекает и добавляет в БД.
- `v` — опциональная версия payload (при расширениях).

### 6.2 Event (events)
```json
{
  "ts": 1730000000,
  "seq": 123456,
  "type": "knx.groupwrite|snapshot|command|state.refresh",
  "ga": "1/1/1",
  "id": 2305,
  "name": "Свет - крыльцо",
  "datatype": 1001,
  "value": true
}
```

Семантика:

seq монотонный счётчик (для диагностики дыр/дубликатов).

type определяет источник/назначение.

6.3 State (state/ga/\*) — retained
```json
{
  "ts": 1730000000,
  "value": true,
  "datatype": 1001
}
```

Семантика:

Для каждого объекта хранится “последняя правда”.

Retain=true позволяет серверу восстановить состояние после рестарта без RPC.

6.4 Meta objects (meta/objects) — retained
```json
{
  "ts": 1730000000,
  "schema_version": 1,
  "schema_hash": "sha256:...",
  "count": 189,
  "objects": [
    {
      "id": 2305,
      "address": "1/1/1",
      "name": "Свет - крыльцо",
      "datatype": 1001,
      "units": "",
      "tags": "mqtt-export,1floor,light",
      "comment": ""
    }
  ]
}
```

Чанки:
meta/objects/chunk/<n>:
```json
{
  "ts": 1730000000,
  "schema_version": 1,
  "schema_hash": "sha256:...",
  "count": 189,
  "chunk_no": 1,
  "chunk_total": 3,
  "objects": [ ... ]
}
```


6.5 Status online/offline (status/online) — retained + LWT

Online:
```json
{ "ts": 1730000000, "status": "online", "version": "1.0.0" }
```

Offline (LWT):
```json
{ "ts": 1730000000, "status": "offline" }
```

6.6 Command (cmd)

Single:
```json
{ "request_id": "uuid", "ga": "1/1/1", "value": 1 }
```

Batch:
```json
{
  "request_id": "uuid",
  "items": [
    { "ga": "1/1/1", "value": 1 },
    { "ga": "2/1/10", "value": 21.5 }
  ]
}
```

6.7 Command ACK (cmd/ack/<request_id>)
```json
{
  "ts": 1730000000,
  "request_id": "uuid",
  "status": "ok|error",
  "results": [
    { "ga": "1/1/1", "applied": true, "error": null }
  ]
}
```


6.8 RPC (service)

REQ:
```json
{
  "request_id": "uuid",
  "method": "snapshot|meta|alerts",
  "params": { "scope": "all|tag:xxx|list", "include": "state|meta|alerts" }
}
```

RESP:
```json
{
  "request_id": "uuid",
  "ok": true,
  "chunk_no": 1,
  "chunk_total": 1,
  "result": { }
}
```

7) Поведение и бизнес-правила
7.1 Клиент (LM App) — бизнес-требования

Стабильная связь с MQTT

LWT настроен до connect.

mqtt.loop() вызывается часто.

События

При изменении объекта публикуется событие в events.

Состояния

Для изменившегося объекта публикуется retained state/ga/*.

Dedup для state допускается (шум не нужен).

Meta

Meta публикуется при старте и по запросу (RPC/кнопка в UI).

При больших объёмах — чанки.

Команды

При получении cmd — выполнить grp.update(ga,value) (виртуальная шина).

Вернуть технический ack.

Отладка

UI позволяет выгрузить нормализованный grp.all() и принудительно отправить meta/snapshot.

7.2 Сервер мониторинга — бизнес-требования

Автодискавери объектов

При получении meta/objects сервер обновляет схему дома.

Если schema_hash новый — фиксирует новую версию схемы.

Состояние

Сервер хранит current state по house_id + ga.

При приходе retained state обновляет store.

История

Сервер пишет events в history store.

Доступность

status=offline → контроллер (device) считается недоступным; если все контроллеры дома offline → дом недоступен; создаётся алерт.

Команды

Команда формируется сервером и отправляется на cmd с request_id.

Ack связывается с командой и сохраняется в истории.

UI/операторский контур

Панель домов: online/offline, последние события, алерты.

Панель объекта: текущее состояние + история.

Панель схемы: объекты/теги/изменения между schema_hash.

8) Хранилища и модели данных (сервер)
8.1 Основные сущности

- House { house_id, created_at, last_seen, online_status }

- Device { house_id, device_id, created_at, last_seen, online_status, is_active }

- Object { house_id, device_id, ga, object_id, name, datatype, units, tags, comment, schema_hash }

- State { house_id, device_id, ga, ts, value, datatype }

- Event { house_id, device_id, ts, seq, type, ga, value, datatype, raw_json }

- SchemaVersion { house_id, device_id, schema_hash, ts, count, raw_meta_json }

- Command { house_id, device_id, request_id, ts_sent, payload, ts_ack, status, results }

- Alert { house_id, type, severity, ts_open, ts_close, context }

8.2 Индексация

State: индекс (house_id, ga) + сортировка по ts.

Events: индекс (house_id, ts) и (house_id, ga, ts).

Commands: индекс (house_id, request_id).

9) Ошибки, дубликаты, идемпотентность
9.1 QoS и дубликаты

QoS1 может давать повтор доставки → сервер должен быть готов к повторным events/state.

Для events: допустимы дубликаты (это журнал); при желании сервер может дедупить по (house_id, ts, ga, value, seq).

9.2 Команды

request_id обеспечивает идемпотентность на сервере (повтор cmd не создаёт новую бизнес-команду).

Клиент ACK отправляет всегда “best effort”; при повторной cmd с тем же request_id клиент может повторно ответить ack (допускается).

9.3 Meta чанки

Сервер собирает чанки по schema_hash + chunk_total.

Если не все чанки пришли — можно запросить rpc meta (или ждать очередной публикации).

10) Наблюдаемость и операционные метрики
10.1 Клиент

queue depth, dropped count

mqtt connected, reconnect count

counters: events/state/meta published, cmd received, cmd ok/error

last_error

10.2 Сервер

ingest rate per house

lag (time now - event.ts)

online/offline transitions

command latency: ts_ack - ts_sent

schema churn: количество изменений схемы


11) Диаграммы последовательностей (Mermaid)
11.1 Подключение LM к MQTT + LWT

```sequenceDiagram
  participant LM as LogicMachine Daemon
  participant B as MQTT Broker
  participant S as Server Ingestor

  LM->>B: CONNECT (will_set status=offline, retain=true)
  B-->>LM: CONNACK
  LM->>B: PUBLISH cm/<house>/<device>/v1/status/online = {"status":"online"} retain=true
  S->>B: SUBSCRIBE cm/+/+/v1/#
  B-->>S: (retained) status=online

  Note over LM,B: Если LM пропадает без DISCONNECT
  B-->>S: PUBLISH (LWT) status=offline retain=true
```

11.2 Событие изменения объекта → events + state
  ```sequenceDiagram
  participant LB as localbus/groupwrite
  participant LM as LogicMachine Daemon
  participant B as MQTT Broker
  participant S as Server Ingestor
  participant DB as State/History DB

  LB-->>LM: object changed (ga,value,datatype)
  LM->>B: PUBLISH cm/<house>/<device>/v1/events (json) qos0
  LM->>B: PUBLISH cm/<house>/<device>/v1/state/ga/<ga> (retained) qos1
  S->>B: SUBSCRIBE cm/+/+/v1/#
  B-->>S: events message
  S->>DB: INSERT Event
  B-->>S: retained state update
  S->>DB: UPSERT State (house_id,ga)
  ```

  11.3 Публикация meta/objects чанками
  ```sequenceDiagram
  participant LM as LogicMachine Daemon
  participant B as MQTT Broker
  participant S as Server Ingestor
  participant R as Schema Registry

  LM->>B: PUBLISH cm/<house>/<device>/v1/meta/objects/chunk/1 retain=true
  LM->>B: PUBLISH cm/<house>/<device>/v1/meta/objects/chunk/2 retain=true
  LM->>B: PUBLISH cm/<house>/<device>/v1/meta/objects/chunk/3 retain=true
  S->>B: SUBSCRIBE cm/+/+/v1/#
  B-->>S: chunks (schema_hash=H)
  S->>R: assemble chunks by H
  R-->>S: schema stored (H)
  ```

  11.4 Команда от сервера → выполнение в LM → ack
  ```sequenceDiagram
  participant UI as Server UI
  participant CS as Command Service
  participant B as MQTT Broker
  participant LM as LogicMachine Daemon
  participant DB as Commands DB

  UI->>CS: send command (ga,value)
  CS->>DB: CREATE Command(request_id)
  CS->>B: PUBLISH cm/<house>/<device>/v1/cmd {request_id,ga,value} qos1
  LM->>B: SUBSCRIBE cm/<house>/<device>/v1/cmd
  B-->>LM: cmd message
  LM->>LM: grp.update(ga,value)
  LM->>B: PUBLISH cm/<house>/<device>/v1/cmd/ack/<request_id> {status,results}
  CS->>B: SUBSCRIBE cm/+/+/v1/cmd/ack/+
  B-->>CS: ack
  CS->>DB: UPDATE Command(status,ts_ack,results)
  ```

  11.5 RPC Snapshot (сервер просит “срез”)
  ```sequenceDiagram
  participant S as Server
  participant B as MQTT Broker
  participant LM as LogicMachine Daemon
  participant DB as State DB

  S->>B: PUBLISH cm/<house>/<device>/v1/rpc/req/<client_id> {method:"snapshot",request_id}
  LM->>B: SUBSCRIBE cm/<house>/<device>/v1/rpc/req/+
  B-->>LM: rpc request
  LM->>LM: build snapshot from grp.all()/cache
  LM->>B: PUBLISH cm/<house>/<device>/v1/state/ga/* (retained) OR rpc/resp
  S->>B: SUBSCRIBE cm/+/+/v1/#
  B-->>S: updates
  S->>DB: UPSERT State
  ```

  12) Требования к Apps UI (клиент)
12.1 UI функции (обязательные)

Настройка: house_id, device_id, MQTT broker, логин/пароль, client_id, QoS, режим команд (update/write).

Фильтры экспорта: теги/список GA.

Надёжность: max_queue, drop_policy, dedup.

Snapshot/meta: кнопки “Publish meta now”, “Publish snapshot now”.

Диагностика: выгрузка нормализованного grp.all().

12.2 Контроль daemon (обязательный)

UI должен давать restart/stop через стандартный Apps request.lp (админ-пароль).

13) План реализации (сервер)
13.1 Минимальный MVP

Broker + ACL per house/device.

Ingestor:

подписка status, state/ga/+, events, meta/objects*, cmd/ack/+.

парсинг JSON, сохранение.

DB:

state table + events table + schema versions + commands.

UI:

список домов (online/offline)

дерево объектов + текущее состояние

лента событий

отправка команды + просмотр ack

13.2 Следующий уровень

Alert rules engine (offline, пороги температур, “нет обновлений N минут”).

Дедуп и нормализация типов.

Диффы схемы и миграции.

14) Риски и меры

Слишком большие meta/snapshot → чанки + лимиты.

Дубликаты QoS1 → идемпотентность по ключам.

Неполная схема при потерях чанков → RPC meta запрос.

Смещение времени → хранить server_received_ts, сравнивать с payload ts.


15) C4 диаграммы (Mermaid)

15.1 C4 Context
```flowchart LR
  subgraph User[Пользователи]
    Op[Оператор/Диспетчер]
    Eng[Инженер/Интегратор]
  end

  subgraph House[Дом]
    LM1[LogicMachine 1\ncm-mqtt-exporter]
    LM2[LogicMachine N\ncm-mqtt-exporter]
    KNXDevices[Устройства/объекты\n(виртуальная шина/KNX)]
  end

  subgraph Cloud[Инфраструктура мониторинга]
    Broker[MQTT Broker]
    Mon[Сервер мониторинга]
  end

  Op -->|UI| Mon
  Eng -->|UI/API| Mon
  KNXDevices -->|state changes| LM1
  KNXDevices -->|state changes| LM2
  LM1 -->|publish| Broker
  LM2 -->|publish| Broker
  Mon -->|subscribe| Broker
  Mon -->|publish cmd| Broker
  Broker -->|deliver cmd| LM1
  Broker -->|deliver cmd| LM2
  ```


15.2 C4 Container

```flowchart TB
  subgraph LMNode[LogicMachine]
    UI[Apps UI\n(index.lp/config.lp)]
    D[Daemon exporter\n(localbus + mqtt)]
    UI -->|config| D
  end

  subgraph Infra[Monitoring Infra]
    B[MQTT Broker]
    I[Ingestor]
    API[API Service]
    FE[Web UI]
    CS[Command Service]
    AE[Alert Engine]
    SS[(State Store)]
    HS[(History Store)]
    SR[(Schema Registry)]
  end

  D -->|pub events/state/meta/status| B
  CS -->|pub cmd| B
  B -->|deliver cmd| D

  I -->|sub all| B
  I --> SS
  I --> HS
  I --> SR
  AE --> SS
  API --> SS
  API --> HS
  API --> SR
  FE --> API
  CS --> API
  AE --> API
  ```
  16) MQTT ACL (пример политики)
16.1 Принцип

У каждого LM контроллера отдельный пользователь (например lm_house-01_lm-main) — может публиковать только исходящие топики своего дома/устройства и подписываться только на входящие (cmd, rpc/req/*).

У сервера отдельный пользователь (например mon_server) — может всё в рамках cm/+/+/v1/#.

16.2 Шаблон ACL (логический)

Для конкретного house_id = H, device_id = D:

LM user (publish allowed):

cm/H/D/v1/events

cm/H/D/v1/state/#

cm/H/D/v1/meta/#

cm/H/D/v1/status/#

cm/H/D/v1/cmd/ack/#

cm/H/D/v1/rpc/resp/#

LM user (subscribe allowed):

cm/H/D/v1/cmd

cm/H/D/v1/rpc/req/#

LM user (deny):

publish на cm/H/D/v1/cmd (запрещено)

publish на cm/H/D/v1/rpc/req/# (запрещено)

Server user (subscribe/publish allowed):

cm/+/+/v1/# (или более узко по списку домов)

16.3 Замечания по безопасности

Если брокер поддерживает “pattern ACL” (например prefix-based), внедрить именно так.

При использовании shared broker для разных клиентов — обязательно изоляция по house_id и device_id.

17) Server API (контракт для UI/интеграций)

API — REST (минимальный), версионирование v1.
Базовый URL: /api/v1

17.1 Аутентификация

Bearer JWT (рекомендуемо) или API key (для MVP).

Роли (минимум): viewer, operator, admin.

17.2 Endpoints
Houses

GET /houses

ответ: список домов, online_status, last_seen, counters

GET /houses/{house_id}

подробности дома, текущая схема (schema_hash), настройки мониторинга

GET /houses/{house_id}/status

online/offline + причины (LWT/offline timeout)

Devices

GET /houses/{house_id}/devices

список контроллеров дома, online_status, last_seen

GET /houses/{house_id}/devices/{device_id}

подробности контроллера

PATCH /houses/{house_id}/devices/{device_id}

деактивация/реактивация контроллера

Objects / Schema

GET /houses/{house_id}/objects

список объектов (из последней schema_version)

фильтры: ?tag=mqtt-export, ?q=light

GET /houses/{house_id}/schemas

история schema_hash, ts, count

GET /houses/{house_id}/schemas/{schema_hash}

конкретная версия объектов + raw_meta_json (опционально)

GET /houses/{house_id}/schemas/diff?from=A&to=B

добавленные/удалённые/изменённые объекты

State (current)

GET /houses/{house_id}/state

все текущие состояния (пагинация/фильтры)

GET /houses/{house_id}/state/{ga}

текущее состояние конкретного объекта

GET /houses/{house_id}/state?ga=1/1/1,1/1/2

батч запрос

Events (history)

GET /houses/{house_id}/events?from=...&to=...&ga=...&type=...

история событий

GET /houses/{house_id}/events/stream

SSE/WebSocket (опционально) для live-ленты

Alerts

GET /houses/{house_id}/alerts?status=open|closed

POST /houses/{house_id}/alerts/rules

создание/обновление правил (порог, no-update timeout)

POST /houses/{house_id}/alerts/{alert_id}/ack

подтверждение оператором

Commands

POST /houses/{house_id}/commands

body:

{ "items": [{ "ga":"1/1/1", "value":1 }], "comment":"optional" }

server:

генерирует request_id

публикует MQTT cmd

сохраняет Command

response:

{ "request_id":"uuid", "status":"sent" }

GET /houses/{house_id}/commands?from=...&to=...

история команд и статусы

GET /houses/{house_id}/commands/{request_id}

детали + ack results

Ops / Diagnostics

POST /houses/{house_id}/devices/{device_id}/rpc/meta

публикует rpc/req на meta для конкретного контроллера (через брокер)

POST /houses/{house_id}/devices/{device_id}/rpc/snapshot

публикует rpc/req на snapshot для конкретного контроллера

GET /health

GET /metrics (Prometheus)

17.3 Ошибки API (единый формат)
{
  "error": {
    "code": "VALIDATION_ERROR|NOT_FOUND|FORBIDDEN|INTERNAL",
    "message": "human readable",
    "details": { }
  }
}

18) Рекомендованный серверный пайплайн (MVP)

MQTT consumer (ingestor)  → DB writer.

Разделить хранение:

State: быстрый KV/SQL upsert

Events: timeseries/партиции по дате

Schema: отдельная таблица версий

Alert Engine:

offline по status=offline

no-update: если now - state.ts > threshold

thresholds: по datatype/ga/tag

19) Риски и меры

Большие meta/snapshot → чанки + лимиты.

Дубликаты QoS1 → idempotency keys + tolerant ingestion.

Несобранные чанки → повтор meta через RPC.

Смещение времени → хранить server_received_ts и сравнивать с payload ts.