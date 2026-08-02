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

Для нашего контроллера (`192.168.100.130`) работает HTTP Basic Auth (пароль — вне git, см. **001 R-012**):
```bash
curl -u admin:*** -H "Referer: http://192.168.100.130/" \
  "http://192.168.100.130/apps/request.lp?action=restart&name=cottage-monitoring"
```

**Веб (LAN)**: user `admin`. **FTP**: user `apps`. Пароли не в git.

```bash
curl -u admin:*** -H "Referer: http://192.168.100.130/" \
  "http://192.168.100.130/apps/request.lp?action=stop&name=cottage-monitoring"
# put daemon.lua …
curl -u admin:*** -H "Referer: http://192.168.100.130/" \
  "http://192.168.100.130/apps/request.lp?action=start&name=cottage-monitoring"
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

**FTP**: `ftp://apps@192.168.100.130` (user `apps`, пароль вне git)  
**Web**: `http://192.168.100.130/` (user `admin`, LAN)

**lftp — вся директория**:
```bash
lftp -u apps,"$LM_FTP_PASSWORD" ftp://192.168.100.130 -e "
cd /data/apps/store/data/cottage-monitoring
lcd cm-client
mirror -R .
bye
"
```

**lftp — один файл**:
```bash
lftp -u apps,"$LM_FTP_PASSWORD" ftp://192.168.100.130 -e "
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

С **июля 2026** certbot renew для `elion.black-castle.ru` выдаёт **YR2** (3 PEM), даже с `preferred_chain = ISRG Root X1`. Deploy-hook раньше брал из archive последний **R12** (2 PEM) — он истёк **10 Aug 2026**, и daily check начал слать Telegram «expires within 14 days», хотя live LE cert был уже до **Oct 2026**.

### Решение

- На mosquitto: `/etc/mosquitto/certs/fullchain.pem` + `privkey.pem` (копия, не live-symlink).
- certbot: `preferred_chain = ISRG Root X1` (оставить; R12 может не выдаваться).
- Deploy-hook `server/scripts/10-mosquitto-cert-hook.sh` → `/etc/letsencrypt/renewal-hooks/deploy/10-mosquitto.sh`:
  1. live == 2 PEM → copy;
  2. live > 2 PEM → валидный 2-block из archive (legacy R12), если срок ≥14 дней;
  3. иначе → **trim** newest fullchain до 2 PEM (leaf + YR2 intermediate), matching privkey из archive.
- **Автообновление включено**; после renew: `server/scripts/check_mosquitto_cert.sh` (2 PEM + запас ≥14 дней).
- Клиент: по умолчанию `tls_insecure`; opt-in `mqtt_tls_verify` + ISRG Root X1 **не покрывает YR2** — verify только с legacy R12 chain.

### Инцидент 2026-07-29

Алерт `FAIL: certificate expires within 14 days` — корректный: mosquitto держал archive `fullchain2` (R12, Aug 10). Fix: force renew + trim `fullchain4` → mosquitto OK до Oct 27; 5–6 MQTT clients после reload.

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

## R-015: Рост CPU после compact daemon — вернуть batching (2026-07-18)

### Контекст

Loadavg LM (`34/1/6` 1‑мин) вырос с ~0.85 avg (14–16.07) до ~1.58 avg с 00:00 17.07 МСК — сразу после compact rewrite v1.1.1. DRM88 не меняли.

В compact daemon убрали чтение `batch_interval` → каждое KNX-событие сразу давало 2 MQTT publish; `hb()` писал storage ×3 каждый цикл (~6–7 Гц).

### Решение (v1.1.2)

- Вернуть event batching (`events/batch` + `state/batch` + retained `state/ga`), defaults `batch_interval=1.5`, `batch_max_size=50`.
- Heartbeat storage раз в 3 с (`HB_INTERVAL`).
- Defaults: `loop_sleep=0.25`, `throttle=20`, `event_sleep=0.03`.
- Yield при flush offline-буфера (каждые 20 msg).

### Альтернативы (отвергнуты / отложены)

- Крутить только sleeps без batching — слабый эффект при активной шине.
- Трогать DRM88 poll — вне scope (скрипт не меняли).

Мониторинг: Grafana дашборд `cottage-lm-load` + алерт load15 > 2.0 — см. **001 R-015**.

---

## R-016: Инцидент 2026-08-02 — телеметрия остановилась, watchdog не восстановил (2026-08-02)

### Симптомы

- С **~13:07 МСК** события в prod-БД (`events` для `house`/`lm-main`) перестали поступать; до этого ~80–110 events/мин.
- Сервер elion здоров (`/health` 200, MQTT ingestor online).
- На LM процесс daemon **жив** (`lua … cottage-monitoring`, PID не менялся с деплоя **~2026-07-18**).
- В MQTT продолжали (и продолжают) публиковаться **`status/health`** раз в 60 с с `mqtt_connected:true`, `uptime` ~14+ суток; **`events/batch`** на брокере **нет** (проверка `mosquitto_sub`, timeout 10 с).
- В **13:09 МСК** на брокере появился retained **`status/offline`** (LWT или краткий обрыв MQTT); затем снова `status/online` / `health`.
- Watchdog **установлен** (Resident `watchdog-cm-mqtt`, `scripting-resident.lua` #73), но **не восстановил телеметрию** в день инцидента.

### Факты с elion (2026-08-02 ~23:50 МСК)

| Проверка | Результат |
|----------|-----------|
| `MAX(server_received_ts)` events `house` | **2026-08-02 13:07:32 МСК** |
| `houses.last_seen` / `devices.last_seen` | то же |
| Логи ingestor 10:05–10:07 UTC | только `status/health` → `unknown_topic` (ожидаемо: парсер не знает health) |
| Логи 10:09 UTC | `status/offline` |
| Prod cottage-monitoring | active, MQTT connected |

### Факты с LM (SSH root, 2026-08-02)

| Проверка | Результат |
|----------|-----------|
| Daemon process | **running** (`/home/apps/store/daemon/cottage-monitoring/daemon.lua`, v1.1.2 от 2026-07-18) |
| Watchdog resident | **running** (есть в `ps`, имя `watchdog-cm-mqtt` в БД LM) |
| История alert в БД LM | многочисленные `hard restart #98…#112 reason=mqtt_offline age=~1310…s` (**~15 суток**) — эпоха **до** июльского фикса MQTT; **свежих** `heartbeat_stale` / `HTTP restart FAILED` в strings не найдено |
| `health_get.lp` с workstation | 401 (нужен **LM admin**, не root SSH) |

### Root cause (5 Why)

1. **Почему в облаке нет телеметрии с ~13:00?**  
   В БД нет новых `events` после 13:07; на MQTT нет `events/batch`, хотя `status/health` идёт.

2. **Почему сервер не получает события?**  
   Клиент LM **не публикует** event/state batch на брокер (ingestor на elion работает).

3. **Почему клиент не публикует, хотя «контроллер живой»?**  
   Процесс daemon **не упал**: главный цикл крутится (heartbeat в storage, health в MQTT), но **цепочка localbus → event_batch → flush_batch** перестала отдавать данные (**«зомби»-режим** — тип, который watchdog изначально задумывал ловить, но см. п.4).

4. **Почему watchdog не перезапустил daemon?**  
   Условия срабатывания (`watchdog-resident.lua`): `heartbeat_stale` (>120 с), `no_heartbeat`, или **`mqtt_offline`** (>600 с при `cm_mqtt_connected=false`).  
   В инциденте **heartbeat свежий** и **MQTT в storage/health = online** → watchdog **считает систему здоровой** и **не эскалирует**.  
   Он **не проверяет**: время последнего `events/batch`, рост `cm_last_event_ts`, расхождение health vs реальной телеметрии.

5. **Почему так спроектирован watchdog и почему это повторяется?**  
   - Спека (R-012, quickstart) описывает только **процесс + MQTT link**, не **end-to-end телеметрию**.  
   - Daemon v1.1.2 пишет `status/health` с **захардкоженным** `mqtt_connected: true` при `S.connected`, что **маскирует** частичные отказы для оператора и для будущих проверок.  
   - LM Apps **не гарантирует** autostart после питания без Config→Save (отдельная проблема, инцидент **2026-04**); watchdog **не заменяет** серверный алерт `cottage-house-stale` (`last_seen` >15m) — тот должен был сработать на elion.  
   - Исторические циклы `mqtt_offline` + hard restart (#100+) не помогли, пока не сделали Config→Save / MQTT-fix в июле — hard restart **перезапускает процесс**, но **не чинит** зависший localbus без полного reload handler.

### Вывод (корневая причина)

**Не «умер демон» (процесс)**, а **деградация телеметрии внутри долгоживущего процесса daemon** при живом MQTT health/heartbeat.  
**Watchdog не сработал по дизайну** — он не мониторит поток событий, только heartbeat и флаг MQTT в storage.

### Пробелы (gap analysis) — что исправлять (отдельная задача)

| # | Пробел | Предлагаемое направление | Статус |
|---|--------|--------------------------|--------|
| G1 | Watchdog не знает про `last_event_ts` | Daemon: `storage.set('cm_last_event_ts', …)` в `flush_batch` / handler; watchdog: авария если MQTT online, но `now - cm_last_event_ts > N` (с grace при отсутствии KNX) | **done v1.1.3** (2026-08-03): daemon пишет `cm_last_event_ts` (baseline при старте, далее в `hb()` piggyback — без роста write rate); watchdog: условие `events_stale` (порог `wd_events_stale_sec`, default 900 c, 0 = off; guard `last_evt > 0` для старых daemon) |
| G2 | Health вводит в заблуждение | Публиковать реальный `mqtt_connected` и добавить `last_event_age_sec` | **частично v1.1.3**: `last_event_age` добавлен в `status/health` (MQTT) и `health_get.lp`; `mqtt_connected` в health по-прежнему публикуется только когда connected (проблема самомаскировки снята полем `last_event_age`) |
| G3 | `cm_last_disconnect_ts` не сбрасывается в `ON_CONNECT` | `storage.set('cm_last_disconnect_ts', 0)` при connect — иначе ложный `mqtt_offline age=15d` при кратковременном `cm_mqtt_connected=false` | **done v1.1.3** |
| G4 | Hard restart без `lm_admin_password` | Watchdog требует `config.set('cottage-monitoring','lm_admin_password',…)` на LM; без этого только soft `cm_force_restart` | open (операционный шаг на LM) |
| G5 | Серверный алерт | Убедиться, что `cottage-house-stale` в Grafana/Prometheus реально доставляет уведомление (по `last_seen`, не по health) | open |
| G6 | Периодический self-heal | Опционально: resident или cron на LM — `restart` daemon раз в N дней; или watchdog по max uptime | open; частично закрыт remote-restart: `POST /houses/{id}/restart-daemon` → cmd `{"action":"restart"}` → ack + самоперезапуск daemon через ~2 с (v1.1.3) |

### Workaround (операционный)

1. **Config → Save** в Apps (как в инциденте 2026-04) — перезапуск daemon с перечитыванием конфига.  
2. Или `./deploy/lm-apps.sh restart` (нужен `secrets/lm.env` с `LM_ADMIN_PASSWORD`).  
3. Проверка: на elion `mosquitto_sub … events/batch` или свежий `last_seen` в БД.

### Дополнение 2026-08-03: фактическая корневая причина (после live-отладки)

Первичный 5 Why (выше) опирался на **retained** `status/health` в MQTT, ошибочно принятый за «живой» поток — его ts был **13:07** (момент обрыва). Реальная картина:

1. **13:05–13:07** — daemon перестал слать трафик; брокер: `Client house-lm-main has exceeded timeout, disconnecting` (keepalive), LWT `status/offline` 13:09.
2. Реконнект **невозможен**: на LM был включён `mqtt_tls_verify=true` (opt-in из R-013), а цепочка брокера с **29.07** — trimmed **YR2** (fullchain4). ISRG Root X1 CA-файл её **не валидирует** → каждый handshake падал: mosquitto log `OpenSSL Error: tlsv1 alert unknown ca` (alert шлёт клиент). Стабильное TLS-соединение, поднятое ещё при R12-цепочке, жило без re-handshake до первого обрыва — поэтому «сломалось не 29.07, а 02.08».
3. **Watchdog работал**: серия hard restart #98…#122 вечером 02.08 (`mqtt_offline`, cooldown 5 мин) — но рестарт **не лечит** несовпадение сертификата, daemon после каждого рестарта снова не мог подключиться.
4. **Фикс**: `tls_verify_off.lp` (возврат к default R-013 `tls_insecure`) + restart → connect с 1-й попытки.

**Вывод (уточнённый):** корневая причина инцидента 2026-08-02 — **`mqtt_tls_verify=true` + ротация цепочки брокера 29.07 (R12 → YR2)**; событие-триггер — обрыв keepalive 13:07. Watchdog по `mqtt_offline` срабатывал, но был бессилен. Условие `events_stale` (G1) остаётся полезным для настоящего «зомби»-сценария (localbus), но данный инцидент им бы не решился.

**Правило:** `mqtt_tls_verify` включать **только** с CA-файлом, покрывающим актуальную цепочку брокера (сейчас YR2); после каждого renew — проверять handshake с LM. По умолчанию — verify off.

Также при деплое v1.1.3 задокументировано: LM-супервизор **не** пересоздаёт убитый resident-процесс; для программного обновления watchdog — **`./deploy/lm-watchdog-update.sh`** (R-017).

---

## R-017: Деплой и обновление на LM без Web UI (2026-08-03)

### Контекст

Операции на контроллере (деплой daemon, обновление Resident watchdog, TLS flags, health) должны выполняться из CI/терминала без входа в браузер LM. SCP не поддерживается.

### Решение

**Секреты:** `secrets/lm.env` (gitignore) — `LM_HOST`, `LM_FTP_*`, `LM_ADMIN_*`; опционально `LM_SSH_USER`, `LM_SSH_PASSWORD` для respawn resident.

**Скрипты (корень репо):**

| Скрипт | Назначение |
|--------|------------|
| `deploy/deploy-lftp.sh` | mirror `cm-client/` → `data/cottage-monitoring` + `daemon.lua` → `daemon/cottage-monitoring` |
| `deploy/lm-apps.sh` | HTTP: `stop`/`start`/`restart`/`pause-wd`/`hold-wd`/`health` (admin + Referer) |
| `deploy/lm-watchdog-update.sh` | Обновить Resident watchdog в таблице `scripting` + respawn процесса |

**Полный цикл daemon:** `pause-wd` → `stop` → `deploy-lftp.sh` → `start` → `health`.

**Resident watchdog (id на проде = 73, имя `watchdog-cm-mqtt`):**

1. FTP: залить `watchdog-resident.lua` как `cm_wd_new.lua` и одноразовый `cm_script_update.lp`.
2. HTTP: выполнить `.lp` — внутри `db:update('scripting', { script = code }, { id = 73 })`.
3. SSH: `rm -f /var/run/gs-resident-73.pid` (иначе spawn откажется — stale pidfile).
4. SSH: `(lua /lib/genohm-scada/core/scripting-resident.lua 73 </dev/null &)` — на LM нет `nohup`.
5. Удалить временные файлы с FTP.

**Почему нельзя только убить процесс:** init **не** respawn'ит resident после `kill`; код в БД обновится, но старый Lua останется в памяти до reboot или ручного spawn.

**Почему нельзя только Web UI:** допустимо для первой установки; для повторяющихся обновлений — FTP+db быстрее и воспроизводимо.

**`.lp` endpoints без UI:** `health_get.lp`, `tls_verify_off.lp`, `tls_verify_on.lp`, `wd_pause.lp`, `wd_hold.lp`, `config_save.lp` (POST JSON).

**SSH vs HTTP:** `health_get.lp` требует Basic Auth **admin** (root SSH не даёт доступ к Apps storage напрямую удобно). `storage_probe.lp` на LM показывает ключи `cm_*` в storage.

**Список resident scripts:** одноразовый probe через `db:getall("SELECT id,name,active FROM scripting WHERE type='resident'")` в `.lp` (см. инцидент 2026-08-03).

### Operational caveats

- Daemon runtime **только** `daemon/cottage-monitoring/daemon.lua`, не `data/.../daemon/`.
- lftp: `set xfer:clobber yes`.
- После renew cert брокера (R-013): проверить handshake с LM; при `tlsv1 alert unknown ca` — `tls_verify_off.lp`.
- Docker server deploy: pin `mcp>=1.0,<2` (mcp 2.0 убрал `mcp.server.fastmcp` — падение 0.2.7 при первой сборке).

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
| R-015 | CPU / batching | v1.1.2: batch + hb 3s + softer sleeps |
| R-016 | Watchdog gap / zombie daemon | heartbeat+MQTT OK ≠ телеметрия; TLS verify+YR2; см. инцидент 2026-08-02 |
| R-017 | Деплой без Web UI | lftp + lm-apps.sh + lm-watchdog-update.sh; resident pidfile respawn |
