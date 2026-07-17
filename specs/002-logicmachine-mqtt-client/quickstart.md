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

Перед деплоем daemon на время приглушить watchdog:
```bash
./deploy/lm-apps.sh pause-wd
# или ./deploy/lm-apps.sh hold-wd
```

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

## Daemon не стартует после питания

По [документации LogicMachine](https://kb.logicmachine.net/misc/apps/) daemon должен запускаться при загрузке. Однако у Dev apps это часто не выполняется:

1. **Первый запуск:** daemon не активен, пока не сохранён конфиг (Config → Save).
2. **После отключения питания:** daemon может не запуститься автоматически.

**Что делать:** Config → Save (можно без изменений) — daemon перезапустится. Альтернатива — HTTP stop/start (см. выше).

---

## Operational notes (2026-07)

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
- На брокере для LM нужна **короткая** цепочка (2 PEM). Автообновление: certbot + hook. Проверка: `server/scripts/check_mosquitto_cert.sh`.

### Агент OpenClaw / Hermes (не LM)

Dial-команды дома (MCP) лучше гонять отдельным OpenClaw-агентом на **gemini-3.5-flash** с минимальным контекстом — см. **001 R-014**. LM daemon на это не влияет.
### Команды и ack (после R-014)

- Ack в `cmd/ack/{request_id}`; в results — `applied` и эхо `value` (для отладки).
- После OFF в MQTT `events`/`state` должно быть `"value":false`, не `null` (см. `safe_getvalue`).

### Учётные данные LM

Пароли — в локальном `secrets/lm.env` (gitignore). В спеках только имена учёток и скрипты `./deploy/deploy-lftp.sh`, `./deploy/lm-apps.sh`. См. **001 R-012**.
