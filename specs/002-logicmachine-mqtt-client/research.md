# Research: Logic Machine MQTT Client App

**Date**: 2026-03-03 | **Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

---

## R-001: Logic Machine Apps — структура и жизненный цикл

### Контекст

Приложение должно быть реализовано как Logic Machine App согласно [kb.logicmachine.net/misc/apps/](https://kb.logicmachine.net/misc/apps/) и docs/apps.pdf (если доступен).

### Решение

**Структура приложения**:
- `config.lp` или `config.html` — форма настроек с events: `config-load`, `config-check`, `config-save`
- `index.lp` — главная страница (обязательна для apps без url)
- `icon.svg` — иконка приложения
- `/daemon/<appname>/daemon.lua` — daemon (хранится в store)

**Config API**:
- `config.get(app, key, default)` — чтение из Lua daemon
- `config.set(app, key, value)` — запись (из LP при POST)
- `config.getall(app)` / `config.setall(app, cfg)` — batch

**Рестарт daemon после config-save**:
```
http://IP/apps/request.lp?password=ADMINPASSWORD&action=restart&name=YOURAPPNAME
```

Для нашего контроллера (`192.168.100.130`) работает HTTP Basic Auth:
```bash
curl -u admin:adminLM123 -H "Referer: http://192.168.100.130/" \
  "http://192.168.100.130/apps/request.lp?action=restart&name=cottage-monitoring"
```

**Веб-доступ (LAN)**: user `admin`, password `adminLM123`.
**FTP**: user `apps`, password `LM_apps123`.
```

Форма после успешного `config-save` инициирует рестарт через `apps/request.lp?action=restart&name=<appname>`.

### Альтернативы

- Хранить конфиг в storage вместо config — отвергнуто: config — стандартный способ для LM Apps.
- Отдельный cron для перезагрузки — отвергнуто: request.lp проще и мгновеннее.

---

## R-002: MQTT клиент (mosquitto) на LogicMachine

### Контекст

[LogicMachine MQTT client (mosquitto)](https://kb.logicmachine.net/libraries/mosquitto/) — Lua-обёртка над libmosquitto.

### Решение

```lua
local mqtt = require('mosquitto')

local client = mqtt.new(client_id, true)  -- clean_session=true
client:login_set(username, password)
client:version_set(mqtt.PROTOCOL_V311)
client:tls_insecure_set(true)  -- для самоподписанных сертификатов (опция)
-- client:tls_set(cafile, capath, certfile, keyfile)  -- для mTLS
client:connect(host, port or 8883, keepalive or 60)
client:subscribe(topic, qos)
client:publish(topic, payload, qos, retain)
client:callback_set('ON_MESSAGE', function(mid, topic, payload, qos, retain, props) ... end)
client:callback_set('ON_CONNECT', ...)
client:callback_set('ON_DISCONNECT', ...)

while true do
  client:loop(1000)  -- 1 s timeout
  -- localbus:step() и др.
  os.sleep(0.1)
end
```

**Особенности**:
- `loop(timeout)` — вызывать часто для обработки сетевых сообщений
- TLS: `tls_set` или `tls_insecure_set(true)` — в зависимости от CA на контроллере
- LWT: `will_set(topic, payload, qos, retain)` до `connect`

### Альтернативы

- MQTT client script (gateways) — отдельный сценарий, не App daemon. Отвергнуто.
- Прямой TCP + ручная реализация MQTT — слишком сложно. Отвергнуто.

---

## R-003: Localbus — прослушивание groupwrite

### Контекст

[LogicMachine localbus](https://kb.logicmachine.net/misc/apps/#server-side-local-bus-monitoring) — серверная библиотека для daemon.

### Решение

```lua
local lb = require('localbus').new(0.5)  -- timeout 0.5 s

lb:sethandler('groupwrite', function(event)
  -- event.datahex, event.dst, event.src, event.type
  -- Декодирование: knxdatatype.decode(event.datahex, dt.XXX)
  -- grp.find(event.dstraw) для name, datatype
end)

lb:sethandler('storage', function(action, key, value) ... end)

while true do
  lb:step()  -- ждёт сообщение или timeout
  -- mqtt:loop(), буфер, snapshot...
  os.sleep(0.05)
end
```

**Интеграция с MQTT loop**:
Цикл: `lb:step()` → `mqtt:loop(100)` → `process_buffer()` → `os.sleep(0.05)`.

### Альтернативы

- Event scripts на каждый GA — не масштабируется для 150+ объектов. Отвергнуто.
- Polling grp.getvalue — задержка и нагрузка. Отвергнуто.

---

## R-004: grp и json — объекты и сериализация

### Контекст

[grp](https://kb.logicmachine.net/libraries/lua/#object-access-and-control), [json](https://kb.logicmachine.net/libraries/lua/#json).

### Решение

- `grp.all()` — все объекты (таблица с полями: address, name, datatype, value, updatetime...)
- `grp.find(alias)` — один объект по адресу или имени
- `grp.getvalue(alias)` — только значение
- `grp.write(alias, value [, datatype])` — запись в шину (для cmd)
- `grp.readvalue(alias [, timeout])` — чтение с ожиданием (для snapshot)
- `require('json')` — `json.encode(value)`, `json.decode(value)`, `json.pdecode(value)` (protected)

**Маппинг datatype KNX → JSON**:
- dt.bool / 1001 → true/false
- dt.scale / 5001 → 0..100
- dt.float16 / 9001 → number
- dt.float32 / 14 → number
- dt.string / 255 → string

### Альтернативы

- Прямая работа с datahex — требуется knxdatatype.decode. Используем grp для декодирования.

---

## R-005: schema_hash и encdec

### Контекст

Сервер ожидает `schema_hash` в meta/objects (SHA256). [encdec](https://kb.logicmachine.net/libraries/lua/) — `require('encdec')` перед использованием.

### Решение

```lua
require('encdec')
local hash = encdec.sha256(json.encode(sorted_objects_array))
-- "sha256:" .. hash (32-char hex)
```

Сортировка объектов по `address` для детерминированности хеша.

### Альтернативы

- MD5 — менее криптостойкий, но быстрее. SHA256 предпочтительнее для совместимости с сервером.

---

## R-006: Логирование — alert() и log()

### Контекст

Пользователь требует: `alert(fmt, ...)` и `log(...)`, включать из конфига.

### Решение

```lua
local debug = toboolean(config.get('cottage-monitoring', 'debug', false))

local function dlog(...)
  if debug then
    log(...)
  end
end

local function dalert(fmt, ...)
  if debug then
    alert(fmt, ...)
  end
end
```

- `log(...)` — человекочитаемый вывод в лог LogicMachine
- `alert(fmt, ...)` — добавляет в список Alert (как string.format)

Использовать `dlog`/`dalert` для отладочных сообщений; критические ошибки (MQTT disconnect, cmd error) логировать всегда.

### Альтернативы

- Всегда log — засоряет лог при production. Отвергнуто.
- Отдельный уровень (debug/info/warn) — избыточно для MVP. Конфиг `debug` достаточно.

---

## R-007: Буфер при отключении MQTT

### Контекст

FR-006a: при недоступности MQTT — буфер в RAM, FIFO, без дедупликации, при переполнении — отбрасывать старые.

### Решение

```lua
local buffer = {}
local buffer_size = tonumber(config.get('cottage-monitoring', 'buffer_size', 1000)) or 1000

local function buf_add(entry)
  if buffer_size == 0 then return end
  table.insert(buffer, entry)
  while #buffer > buffer_size do
    table.remove(buffer, 1)
  end
end

local function buf_flush()
  while #buffer > 0 do
    local e = table.remove(buffer, 1)
    mqtt_publish(e.topic, e.payload, e.qos, e.retain)
  end
end
```

Тип записи: `{topic, payload, qos, retain}`. При восстановлении соединения (ON_CONNECT) — `buf_flush()`.

### Альтернативы

- storage вместо RAM — сохраняет при перезагрузке, но медленнее и ограничения по размеру. spec требует RAM. Отвергнуто для буфера.
- Дедупликация по GA — spec явно требует «без дедупликации». Отвергнуто.

---

## R-008: Чанковая публикация meta ( count > 100)

### Контекст

FR-003: при >100 объектах — meta в чанках `meta/objects/chunk/N`.

### Решение

```lua
local CHUNK_SIZE = 50  -- или 100
local objects = grp.all()
local count = #objects
local chunk_total = math.ceil(count / CHUNK_SIZE)

for chunk_no = 1, chunk_total do
  local start = (chunk_no - 1) * CHUNK_SIZE + 1
  local finish = math.min(start + CHUNK_SIZE - 1, count)
  local chunk_objs = {}
  for i = start, finish do
    table.insert(chunk_objs, format_object(objects[i]))
  end
  local topic = base_topic .. '/meta/objects/chunk/' .. chunk_no
  local payload = json.encode({
    ts = os.time(),
    schema_hash = schema_hash,
    count = count,
    chunk_no = chunk_no,
    chunk_total = chunk_total,
    objects = chunk_objs
  })
  publish(topic, payload, 1, true)
end
```

### Альтернативы

- Один топик с большим payload — ограничения MQTT на размер сообщения. Чанки надёжнее.

---

## R-009: TLS на LogicMachine

### Контекст

FR-010: TLS обязателен. На контроллере может не быть корневых сертификатов для проверки сервера.

### Решение

- `tls_insecure_set(true)` — пропуск проверки сертификата сервера (для самоподписанных/внутренних CA)
- Альтернатива: положить CA-сертификат на контроллер и использовать `tls_set(cafile, nil, nil, nil)`

Для MVP — `tls_insecure_set(true)` с явным предупреждением в документации (внутренняя сеть). Для production — рекомендуется настроить CA.

### Альтернативы

- Без TLS — нарушение FR-010. Отвергнуто.
- mTLS (клиентский сертификат) — усложняет настройку. Отложено.

---

## R-010: Деплой через lftp (FTP)

### Контекст

Контроллер **не поддерживает SCP**. Используется FTP через lftp: `ftp://apps@192.168.100.130`.

### Решение

**Целевой путь на LogicMachine**: `/data/apps/store/data/cottage-monitoring/`

**FTP**: `ftp://apps@192.168.100.130` (user `apps`, password `LM_apps123`)  
**Web**: `http://192.168.100.130/` (user `admin`, password `adminLM123`, LAN)

**lftp — вся директория**:
```bash
lftp -u apps,LM_apps123 ftp://192.168.100.130 -e "
cd /data/apps/store/data/cottage-monitoring
lcd cm-client
mirror -R .
bye
"
```

**lftp — один файл**:
```bash
lftp -u apps,LM_apps123 ftp://192.168.100.130 -e "
cd /data/apps/store/data/cottage-monitoring/daemon
lcd cm-client/daemon
put daemon.lua
bye
"
```

После загрузки — установка приложения через веб-интерфейс LogicMachine (Apps → Install from directory) или вручную регистрация daemon.

### Альтернативы

- SCP — не поддерживается контроллером. Отвергнуто.
- OTA через MQTT — не предусмотрено в LM Apps. Отвергнуто.

---

## R-011: Runtime-путь daemon и лимиты Lua на LM (2026-07)

### Контекст

Деплой в `data/cottage-monitoring/daemon/` не подхватывается Apps. После рестарта работал старый код.

### Решение

- Runtime: **`/daemon/cottage-monitoring/daemon.lua`** (FTP: `daemon/cottage-monitoring`).
- Надёжный цикл деплоя: `stop` → `put` → `start` (не полагаться на `restart`).
- Слишком большой daemon / много top-level `local` — процесс не стартует. Держать компактный код (таблицы конфига/состояния, меньше локалей). Рабочий размер порядка ~10KB.

---

## R-012: mosquitto `loop()` на LM — handshake и код возврата (2026-07)

### Контекст

При reconnect без вызова `loop()` TCP к :8883 устанавливался, но MQTT/TLS не завершался (`ON_CONNECT` не приходил). После «успешного» connect код трактовал `loop()==true` как ошибку (`true ~= 0`) и устраивал reconnect-storm.

### Решение

1. Вызывать `client:loop(timeout)` **на каждой итерации**, и online, и offline.
2. Ошибкой считать только `type(rc) == 'number' and rc ~= 0`.
3. Heartbeat/`cm_mqtt_connected` писать каждый цикл; watchdog soft→hard по stale heartbeat / mqtt offline >10 мин.

---

## R-013: TLS-цепочка брокера, совместимая с LM (2026-07)

### Контекст

Let's Encrypt live `fullchain` с intermediate **YR2** (3 PEM) ломает handshake на старом OpenSSL LogicMachine. Короткая цепочка **R12** (2 PEM) работает.

### Решение

- На mosquitto: `/etc/mosquitto/certs/fullchain.pem` + `privkey.pem` (копия, не live-symlink).
- certbot: `preferred_chain = ISRG Root X1`.
- Deploy-hook `10-mosquitto.sh`: если live >2 блоков — взять валидный 2-block из archive, copy + reload mosquitto.
- **Автообновление включено**; после renew проверять `grep -c BEGIN` == 2 в mosquitto certs.
- Клиент: по умолчанию `tls_insecure`; opt-in `mqtt_tls_verify` / `mqtt_cafile`.

---

## R-014: Boolean `false` в Lua и топик cmd/ack (2026-07)

### Контекст

Инцидент: бот включил свет в холле 2 этажа, затем команда «выключить 2 этаж» / разбор — сервер показывал `timeout`, в `current_state`/`events` для bool OFF уходили `null`, физика и телеметрия расходились.

Две отдельные ошибки в компактном daemon:

1. **Ack-топик.** Публикация в голый `cmd/ack` — сервер ждёт `cmd/ack/{request_id}` (`topic_parser` / FR-021). `grp.write` на LM при этом мог выполниться, но команда в БД оставалась `timeout`.
2. **Идиома `ok and v or nil`.** В Lua при `v == false` выражение даёт `nil`. Использовалось после `pcall(grp.getvalue, …)` в snapshot и в localbus handler → MQTT `events`/`state` для выключенного света без `value` или с `null`, БД портилась.

### Решение

- Ack: `(rid ~= '') and ('cmd/ack/' .. rid) or 'cmd/ack'` — всегда с `request_id`, когда он есть.
- `safe_getvalue(addr)`: `if okv then return v end` (не `ok and v or nil`).
- `coerce_cmd_value` для `0`/`1`/`"true"`/`"false"`; **не** маппить `nil→false` (ломает уставки/non-bool).
- В ack results можно эхоить применённый `value` для отладки.

### Проверка

После `grp.write(…, false)` в MQTT должно быть `"value":false` (не отсутствие поля / `null`). Команда через API → статус `ok`, не `timeout`.

---

## Сводка решений

| ID | Тема | Решение |
|----|------|---------|
| R-001 | LM Apps структура | config.lp, index.lp, daemon; config.get/set; request.lp restart |
| R-002 | MQTT | mosquitto, loop, TLS, LWT |
| R-003 | Localbus | lb:step(), sethandler groupwrite |
| R-004 | grp/json | grp.all, grp.write, json.encode |
| R-005 | schema_hash | encdec.sha256 |
| R-006 | Логирование | dlog/dalert при config.debug |
| R-007 | Буфер offline | RAM table, FIFO, buffer_size |
| R-008 | Meta чанки | chunk по 50–100 объектов |
| R-009 | TLS | tls_insecure по умолчанию; verify opt-in |
| R-010 | Деплой | lftp → `daemon/cottage-monitoring` + `data/cottage-monitoring` |
| R-011 | LM limits | компактный daemon, stop/start, runtime path |
| R-012 | loop() | всегда pump; numeric rc only |
| R-013 | Broker cert | short-chain + certbot hook auto-renew |
| R-014 | bool false / ack | `safe_getvalue`; `cmd/ack/{request_id}` |
