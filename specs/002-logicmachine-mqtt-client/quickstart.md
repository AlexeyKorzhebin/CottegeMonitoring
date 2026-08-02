# Quickstart: Logic Machine MQTT Client App

**Feature**: 002-logicmachine-mqtt-client  
**Целевая платформа**: LogicMachine controller

---

## Предварительные требования

- LogicMachine с поддержкой Apps и MQTT (mosquitto library)
- **Доступ к контроллеру**: FTP `ftp://apps@192.168.100.130`, рабочая директория `/data/apps/store/data/cottage-monitoring` (SCP не поддерживается)
- **FTP / веб LM**: учётки `apps` / `admin`; пароли в локальном `secrets/lm.env` (gitignore), см. `secrets/lm.env.example` и **001 R-012**
- **Рестарт daemon**: надёжнее **stop → upload → start**:
  ```bash
  ./deploy/lm-apps.sh pause-wd
  ./deploy/lm-apps.sh stop
  ./deploy/deploy-lftp.sh
  ./deploy/lm-apps.sh start
  ./deploy/lm-apps.sh health
  ```
- MQTT-брокер: `elion.black-castle.ru:8883` (TLS), user `lm_estate`, ACL только `cm/house/#`
- Health JSON: `http://192.168.100.130/apps/data/cottage-monitoring/health_get.lp` (Basic Auth + Referer)

---

## Установка

### 1. Копирование файлов на контроллер

Контроллер не поддерживает SCP, используется **lftp** (FTP).

**Критично:** runtime daemon читается из **`/daemon/cottage-monitoring/daemon.lua`**, не из `data/cottage-monitoring/daemon/`. Заливать нужно в FTP-путь `daemon/cottage-monitoring`.

**Рекомендуется** — скрипт деплоя (читает `secrets/lm.env`):
```bash
./deploy/deploy-lftp.sh
```

**Вручную** (после `source secrets/lm.env`):
```bash
lftp -u "$LM_FTP_USER","$LM_FTP_PASSWORD" "ftp://$LM_HOST" -e "
set xfer:clobber yes
cd data/cottage-monitoring
lcd cm-client
mirror -R .
bye
"
```

**Один файл** (daemon):
```bash
source secrets/lm.env
lftp -u "$LM_FTP_USER","$LM_FTP_PASSWORD" "ftp://$LM_HOST" -e "
set xfer:clobber yes
cd daemon/cottage-monitoring
lcd cm-client/daemon
put daemon.lua
bye
"
```

**Интерактивно**:
```bash
source secrets/lm.env
lftp -u "$LM_FTP_USER","$LM_FTP_PASSWORD" "ftp://$LM_HOST"
cd data/cottage-monitoring
lcd cm-client
mirror -R .
# или один файл: cd daemon; put ../daemon/daemon.lua
bye
```

### 2. Установка приложения

В веб-интерфейсе LogicMachine: **Settings → Apps → Install** (если приложение в Dev apps) или копирование в нужную директорию store.

### 3. Регистрация daemon

Daemon автоматически регистрируется при установке приложения. Путь: `/daemon/cottage-monitoring/daemon.lua`.

**Важно:** Daemon **не стартует при загрузке контроллера**, пока конфигурация не сохранена. Для Dev apps LM запускает daemon только после первого сохранения конфига (Config → Save). После отключения питания daemon может не подняться автоматически — в этом случае откройте приложение → Config → Save (достаточно сохранить без изменений).

---

## Настройка

1. Открыть **Settings → Apps** в веб-интерфейсе LM
2. В разделе **Dev apps** найти **Cottage Monitoring**, нажать на иконку (откроется главная страница)
3. Открыть **Config** — иконка шестерёнки в заголовке приложения (или пункт меню). *Примечание*: Config открывается в модальном окне; при первом запуске поля будут пустыми.
4. Заполнить обязательные поля (рекомендуемые значения для prod):
   - **house_id**: `house`
   - **device_id**: `lm-main`
   - **env_mode**: `prod`
   - **mqtt_host**: `elion.black-castle.ru`
   - **mqtt_port**: `8883`
   - **mqtt_username** / **mqtt_password**: учётные данные MQTT (напр. `lm_estate`)
5. Опционально: client_id (`auto`), buffer_size (1000), batch_interval (1.5), throttle (20), loop_sleep (0.25), event_sleep (0.03)
6. Нажать **Save** — daemon перезапустится автоматически

Для снижения CPU: кнопка «Применить настройки для снижения нагрузки» / `apply_lowload.lp` (batch + throttle + sleeps).

---

## Проверка работы

1. **Health**: `health_get.lp` → `mqtt_connected:true`, растущий `heartbeat`, стабильный `started_ts`
2. **MQTT → сервер**: на elion в логах `schema_processed` / `device_status_updated`; в БД `houses.last_seen` свежий
3. **Команды (обратно)**: `POST /api/v1/houses/house/commands` (API key + write scope) или тест с localhost MQTT:
   ```bash
   mosquitto_pub -h 127.0.0.1 -p 1883 -t 'cm/house/lm-main/v1/cmd' \
     -m '{"request_id":"t1","ga":"1/1/1","value":false}'
   # ack: cm/house/lm-main/v1/cmd/ack/t1   (не голый cmd/ack — иначе timeout на сервере)
   ```
   Bool `false` в events/state должен остаться `false`, не `null` (см. research R-014: нельзя `ok and v or nil` в Lua).

### Watchdog (Resident)

Скрипт `cm-client/scripts/watchdog-resident.lua` — soft (`cm_force_restart`) → hard (HTTP restart), cooldown 5 мин.

**Установка:** Scripting → Resident (первый раз) **или** без Web UI — `./deploy/lm-watchdog-update.sh` (см. раздел ниже).

**Что ловит:** `heartbeat_stale` (>120 с), `no_heartbeat`, `mqtt_offline` (>600 с при `cm_mqtt_connected=false`).

**Что НЕ ловил до v1.1.3 (инцидент 2026-08-02, R-016):** процесс жив, MQTT/health online, heartbeat свежий, но **нет `events/batch`** — «зомби» localbus/батч. С **daemon v1.1.3 + обновлённым watchdog** ловится условием `events_stale`: MQTT online, а `cm_last_event_ts` старше `wd_events_stale_sec` (default **900 с**; `config.set('cottage-monitoring','wd_events_stale_sec', N)`, 0 = выключить). Для старых daemon (< v1.1.3, нет ключа) проверка не активируется. Серверный индикатор — `houses.last_seen` / алерт `cottage-house-stale` (001 quickstart).

**Hard restart:** на LM задать `config.set('cottage-monitoring', 'lm_admin_password', '…')` (не в git); иначе только soft-путь.

Перед деплоем daemon на время приглушить watchdog:
```bash
./deploy/lm-apps.sh pause-wd
# или ./deploy/lm-apps.sh hold-wd
```

**Workaround при пропаже телеметрии:** Config → Save (перезапуск daemon), `./deploy/lm-apps.sh restart`, или **удалённо через API** (daemon >= v1.1.3):
```bash
curl -X POST https://monitoring.black-castle.ru/api/v1/houses/house/restart-daemon \
  -H "Authorization: Bearer <API_KEY_WRITE>" -H 'Content-Type: application/json' \
  -d '{"comment":"recover zombie telemetry"}'
```
Проверка: `mosquitto_sub … cm/house/lm-main/v1/events/batch` на elion или свежий `last_seen` в БД.

---

## Ручные действия (index.lp)

- **Выгрузить в файл** — скачивание JSON с meta/objects и текущими значениями
- **Выгрузить в MQTT** — принудительная публикация meta + snapshot (требует подключённый MQTT)
- **Параметры подключения** — раскрываемая форма с дубликатом config (house_id, device_id, MQTT и др.), сохраняет через config_save.lp

---

## Деплой

```bash
./deploy/deploy-lftp.sh
```

Скрипт загружает приложение в `data/cottage-monitoring` и daemon в `daemon/cottage-monitoring`. Пароли — из `secrets/lm.env` (не в git; см. **001 R-012**).

---

## Обновление на LM без Web UI

Все команды — из корня репозитория, после `cp secrets/lm.env.example secrets/lm.env` и заполнения паролей. Подробности и находки — **R-017** в `research.md`.

### Учётки и пути

| Роль | Учётка | Где взять пароль |
|------|--------|------------------|
| FTP (заливка файлов) | `apps` | `LM_FTP_PASSWORD` в `secrets/lm.env` |
| HTTP Apps API (stop/start/health, `.lp`) | `admin` | `LM_ADMIN_PASSWORD` в `secrets/lm.env` |
| SSH (respawn Resident, опционально) | `root` | ключ `~/.ssh/config` → `lm_estate` или `LM_SSH_PASSWORD` |

| Что | FTP-путь | Runtime на LM |
|-----|----------|---------------|
| UI, `.lp`, health | `data/cottage-monitoring/` | `/home/apps/store/data/cottage-monitoring/` |
| Daemon (обязательно сюда) | `daemon/cottage-monitoring/daemon.lua` | `/home/apps/store/daemon/cottage-monitoring/daemon.lua` |

**SCP на LM не работает** — только lftp/FTP.

### Daemon + приложение (полный цикл)

```bash
./deploy/lm-apps.sh pause-wd    # не дать watchdog рестартить во время деплоя
./deploy/lm-apps.sh stop
./deploy/deploy-lftp.sh         # data/ + daemon/
./deploy/lm-apps.sh start
./deploy/lm-apps.sh health      # mqtt_connected, last_event_age
```

Один файл daemon без полного mirror:

```bash
source secrets/lm.env
./deploy/lm-apps.sh pause-wd && ./deploy/lm-apps.sh stop
lftp -u "$LM_FTP_USER","$LM_FTP_PASSWORD" "ftp://$LM_HOST" -e "
set xfer:clobber yes
cd daemon/cottage-monitoring
lcd cm-client/daemon
put daemon.lua
bye
"
./deploy/lm-apps.sh start && ./deploy/lm-apps.sh health
```

### Resident watchdog (без Scripting → Resident в браузере)

На проде: имя `watchdog-cm-mqtt`, **id=73**, sleep 60 с.

```bash
./deploy/lm-watchdog-update.sh      # id 73 по умолчанию
./deploy/lm-watchdog-update.sh 73   # явный id
```

Скрипт: FTP → `cm_wd_new.lua` + одноразовый `cm_script_update.lp` → `db:update('scripting', …)` → удаление stale `/var/run/gs-resident-73.pid` → spawn `lua /lib/genohm-scada/core/scripting-resident.lua 73`.

**Важно:** LM **не** пересоздаёт убитый resident-процесс сам (только при reboot). После `kill` без respawn watchdog молчит, хотя код в БД уже новый.

Проверка id и имени resident (одноразовый probe через FTP, см. R-017):

```bash
# загрузить probe, выполнить curl, удалить — или смотреть ps:
ssh root@192.168.100.130 "ps w | grep scripting-resident"
```

### Конфиг и TLS без Web UI

| Действие | HTTP (admin + Referer) |
|----------|-------------------------|
| Отключить TLS verify (после смены цепочки брокера) | `GET …/tls_verify_off.lp` |
| Включить TLS verify (только с подходящим CA) | `GET …/tls_verify_on.lp` |
| Пауза watchdog на 5 мин | `./deploy/lm-apps.sh pause-wd` |
| Сохранить конфиг JSON | `POST …/config_save.lp` body `config={…}` |

Пример TLS off + restart:

```bash
source secrets/lm.env
curl -sS -u "$LM_ADMIN_USER:$LM_ADMIN_PASSWORD" -H "Referer: http://$LM_HOST/apps/" \
  "http://$LM_HOST/apps/data/cottage-monitoring/tls_verify_off.lp"
./deploy/lm-apps.sh restart
```

Hard restart watchdog требует на LM (один раз, Scripting console или через config):

```lua
config.set('cottage-monitoring', 'lm_admin_password', '…')
```

### Удалённый рестарт daemon (с сервера, без FTP)

Daemon >= v1.1.3, API write scope:

```bash
curl -X POST https://monitoring.black-castle.ru/api/v1/houses/house/restart-daemon \
  -H "Authorization: Bearer <API_KEY>" -H 'Content-Type: application/json' \
  -d '{"comment":"recover"}'
```

### Проверка телеметрии end-to-end

```bash
./deploy/lm-apps.sh health
# last_event_age должен быть малым; mqtt_connected: true

ssh elion "timeout 10 mosquitto_sub -h 127.0.0.1 -p 1883 -t 'cm/house/lm-main/v1/events/batch' -C 1"
ssh elion "sudo -u postgres psql -d cottage_monitoring -t -c \
  \"SELECT MAX(server_received_ts) FROM events WHERE house_id='house';\""
```

### Типичные ошибки (находки 2026-08)

| Симптом | Причина | Действие |
|---------|---------|----------|
| `mqtt_connected: false`, reconnect растёт | `mqtt_tls_verify=true` + цепочка YR2 на брокере | `tls_verify_off.lp` + restart |
| mosquitto: `tlsv1 alert unknown ca` | то же | verify off или CA под YR2 |
| health в MQTT «живой», events нет | retained `status/health` со старым ts | смотреть `last_event_age` / `events/batch` |
| watchdog hard restart не помогает | TLS/не тот сценарий | не путать с «зомби» localbus |
| Resident не стартует после kill | stale `gs-resident-N.pid` | `rm` pidfile + manual spawn (R-017) |
| Деплой в `data/.../daemon/` | неверный путь | только `daemon/cottage-monitoring/` |

---

## Daemon не стартует после питания

По [документации LogicMachine](https://kb.logicmachine.net/misc/apps/) daemon должен запускаться при загрузке. Однако у Dev apps это часто не выполняется:

1. **Первый запуск:** daemon не активен, пока не сохранён конфиг (Config → Save).
2. **После отключения питания:** daemon может не запуститься автоматически.

**Что делать:** Config → Save (можно без изменений) — daemon перезапустится. Альтернатива — HTTP stop/start (см. выше).

---

## Operational notes (2026-07/08)

### Daemon v1.1.3 — events_stale watchdog + remote restart (2026-08-03)

Ответ на R-016 (зомби-телеметрия 2026-08-02):

- Daemon пишет `cm_last_event_ts` (baseline при старте; обновление при каждом localbus-событии, персист через `hb()` раз в ~3 с — без роста нагрузки на storage).
- `status/health` и `health_get.lp` содержат `last_event_age` — видно «жив, но молчит».
- `ON_CONNECT` сбрасывает `cm_last_disconnect_ts` (исключает ложный многодневный `mqtt_offline`).
- Команда `{"action":"restart"}` в `cmd`: ack → самоперезапуск через ~2 с (через `error('cm_force_restart_remote')`). Серверный API: `POST /api/v1/houses/{house_id}/restart-daemon`.
- Watchdog: новое условие `events_stale` (default 900 с, `wd_events_stale_sec`); `wd_pause.lp`/`wd_hold.lp` также сбрасывают `cm_last_event_ts`.
- **Деплой:** обновить daemon (`deploy-lftp.sh`) и watchdog (`deploy/lm-watchdog-update.sh`); Web UI не обязателен — см. **R-017**.

### Daemon v1.1.2 — CPU / event batching (2026-07-18)

После compact rewrite v1.1.1 loadavg на LM вырос ~×1.8 (GA `34/1/6..8`). Причины: immediate dual-publish на каждое KNX-событие + `storage.set` heartbeat каждый цикл.

v1.1.2:
- **Event batching** снова активен: `batch_interval` (default 1.5) / `batch_max_size` (50) → `events/batch` + `state/batch` + retained `state/ga/*`
- Heartbeat в storage раз в **3 с** (watchdog stale = 120 с)
- Defaults: `loop_sleep=0.25`, `throttle=20`, `event_sleep=0.03`
- Offline buffer flush с yield каждые 20 msg
- Boot marker: `cm_boot=v112_start`

### Daemon v1.1.1 — надёжность MQTT на LM

- **Всегда** вызывать `client:loop(...)` даже пока offline — иначе TLS handshake не завершится и `ON_CONNECT` не придёт.
- Возврат `loop()` на LM часто `true` (успех). Ошибкой считать **только** `type(rc)=='number' and rc~=0`. Иначе reconnect-storm.
- Полный «толстый» daemon (~25KB, десятки top-level `local`) на этой LM может не стартовать; рабочий путь — компактный код (таблицы `C`/`S`, меньше локалей). Текущий runtime ~10KB: MQTT + localbus + meta/cmd + batch.
- Деплой: `set xfer:clobber yes` в lftp, путь `daemon/cottage-monitoring/daemon.lua`.

### TLS к брокеру

- Клиент по умолчанию: `tls_insecure_set(true)`. Opt-in: `mqtt_tls_verify=true` + `mqtt_cafile` (ISRG Root X1 в `certs/isrg-root-x1.pem`). Включить: `tls_verify_on.lp`, откат: `tls_verify_off.lp`.
- **2026-08-03: verify ВЫКЛЮЧЕН** (`tls_verify_off.lp`) — причина инцидента 02.08: verify + YR2-цепочка (после renew 29.07) = `tlsv1 alert unknown ca`, реконнект невозможен (R-016, дополнение). Не включать без CA, покрывающего текущую цепочку брокера.
- На брокере для LM нужна **короткая** цепочка (2 PEM). Автообновление: certbot + hook. Проверка: `server/scripts/check_mosquitto_cert.sh`.

### Агент OpenClaw / Hermes (не LM)

Dial-команды дома (MCP) лучше гонять отдельным OpenClaw-агентом на **gemini-3.5-flash** с минимальным контекстом — см. **001 R-014**. LM daemon на это не влияет.
### Команды и ack (после R-014)

- Ack в `cmd/ack/{request_id}`; в results — `applied` и эхо `value` (для отладки).
- После OFF в MQTT `events`/`state` должно быть `"value":false`, не `null` (см. `safe_getvalue`).

### Учётные данные LM

Пароли — в локальном `secrets/lm.env` (gitignore). В спеках только имена учёток и скрипты `./deploy/deploy-lftp.sh`, `./deploy/lm-apps.sh`. См. **001 R-012**.

### Инцидент: телеметрия остановилась (2026-08-02)

- **Корневая причина (уточнено 03.08):** `mqtt_tls_verify=true` + renew цепочки брокера 29.07 (R12→YR2) → реконнект невозможен; триггер — keepalive timeout ~13:07 МСК. Подробно — **R-016** (дополнение).
- **Фикс:** `tls_verify_off.lp` + restart; для профилактики — `events_stale` в watchdog (v1.1.3).
- **Обход:** `./deploy/lm-apps.sh restart`, `POST …/restart-daemon`, или Config→Save.
