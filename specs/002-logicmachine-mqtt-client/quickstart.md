# Quickstart: Logic Machine MQTT Client App

**Feature**: 002-logicmachine-mqtt-client  
**Целевая платформа**: LogicMachine controller

---

## Предварительные требования

- LogicMachine с поддержкой Apps и MQTT (mosquitto library)
- **Доступ к контроллеру**: FTP `ftp://apps@192.168.100.130`, рабочая директория `/data/apps/store/data/cottage-monitoring` (SCP не поддерживается)
- **FTP-учётные данные**: user `apps`, password `LM_apps123`
- **Веб-интерфейс LM** (`http://192.168.100.130/`): user `admin`, password `adminLM123` (локальная сеть)
- **Рестарт daemon**: надёжнее **stop → upload → start**, чем `restart` (restart иногда не убивает старый процесс):
  ```bash
  curl -u admin:adminLM123 -H "Referer: http://192.168.100.130/" \
    "http://192.168.100.130/apps/request.lp?action=stop&name=cottage-monitoring"
  # …залить daemon.lua…
  curl -u admin:adminLM123 -H "Referer: http://192.168.100.130/" \
    "http://192.168.100.130/apps/request.lp?action=start&name=cottage-monitoring"
  ```
- MQTT-брокер: `elion.black-castle.ru:8883` (TLS), user `lm_estate`, ACL только `cm/house/#`
- Health JSON: `http://192.168.100.130/apps/data/cottage-monitoring/health_get.lp` (Basic Auth + Referer)

---

## Установка

### 1. Копирование файлов на контроллер

Контроллер не поддерживает SCP, используется **lftp** (FTP).

**Критично:** runtime daemon читается из **`/daemon/cottage-monitoring/daemon.lua`**, не из `data/cottage-monitoring/daemon/`. Заливать нужно в FTP-путь `daemon/cottage-monitoring`.

**Рекомендуется** — скрипт деплоя (загружает приложение и daemon):
```bash
./deploy/deploy-lftp.sh 192.168.100.130 apps LM_apps123
```

**Вручную (вся директория)**:
```bash
lftp -u apps,LM_apps123 ftp://192.168.100.130 -e "
set xfer:clobber yes
cd data/cottage-monitoring
lcd cm-client
mirror -R .
bye
"
```

**Один файл** (обновлённый daemon — правильный путь):
```bash
lftp -u apps,LM_apps123 ftp://192.168.100.130 -e "
set xfer:clobber yes
cd daemon/cottage-monitoring
lcd cm-client/daemon
put daemon.lua
bye
"
```

**Интерактивно**:
```bash
lftp -u apps,LM_apps123 ftp://192.168.100.130
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
5. Опционально: client_id (`auto`), debug, buffer_size (1000), snapshot_interval (0), throttle (0)
6. Нажать **Save** — daemon перезапустится автоматически

---

## Проверка работы

1. **Health**: `health_get.lp` → `mqtt_connected:true`, растущий `heartbeat`, стабильный `started_ts`
2. **MQTT → сервер**: на elion в логах `schema_processed` / `device_status_updated`; в БД `houses.last_seen` свежий
3. **Команды (обратно)**: `POST /api/v1/houses/house/commands` (API key + write scope) или тест с localhost MQTT:
   ```bash
   mosquitto_pub -h 127.0.0.1 -p 1883 -t 'cm/house/lm-main/v1/cmd' \
     -m '{"request_id":"t1","ga":"1/1/1","value":false}'
   # ack: cm/house/lm-main/v1/cmd/ack
   ```

### Watchdog (Resident)

Скрипт `cm-client/scripts/watchdog-resident.lua` — soft (`cm_force_restart`) → hard (HTTP restart), cooldown 5 мин.

Перед деплоем daemon на время приглушить watchdog:
```bash
curl -u admin:adminLM123 -H "Referer: http://192.168.100.130/apps/" \
  "http://192.168.100.130/apps/data/cottage-monitoring/wd_pause.lp"
# или wd_hold.lp — без фейкового mqtt_connected
```

---

## Ручные действия (index.lp)

- **Выгрузить в файл** — скачивание JSON с meta/objects и текущими значениями
- **Выгрузить в MQTT** — принудительная публикация meta + snapshot (требует подключённый MQTT)
- **Параметры подключения** — раскрываемая форма с дубликатом config (house_id, device_id, MQTT и др.), сохраняет через config_save.lp

---

## Деплой

```bash
./deploy/deploy-lftp.sh 192.168.100.130 apps LM_apps123
```

Скрипт загружает приложение в `data/cottage-monitoring` и daemon в `daemon/cottage-monitoring` (путь, ожидаемый LM для автозапуска).

*(Временный пароль для dev; при смене пароля — обновить здесь и в других спеках.)*

---

## Daemon не стартует после питания

По [документации LogicMachine](https://kb.logicmachine.net/misc/apps/) daemon должен запускаться при загрузке. Однако у Dev apps это часто не выполняется:

1. **Первый запуск:** daemon не активен, пока не сохранён конфиг (Config → Save).
2. **После отключения питания:** daemon может не запуститься автоматически.

**Что делать:** Config → Save (можно без изменений) — daemon перезапустится. Альтернатива — HTTP stop/start (см. выше).

---

## Operational notes (2026-07)

### Daemon v1.1.1 — надёжность MQTT на LM

- **Всегда** вызывать `client:loop(...)` даже пока offline — иначе TLS handshake не завершится и `ON_CONNECT` не придёт.
- Возврат `loop()` на LM часто `true` (успех). Ошибкой считать **только** `type(rc)=='number' and rc~=0`. Иначе reconnect-storm.
- Полный «толстый» daemon (~25KB, десятки top-level `local`) на этой LM может не стартовать; рабочий путь — компактный код (таблицы `C`/`S`, меньше локалей). Текущий runtime ~10KB: MQTT + localbus + meta/cmd.
- Деплой: `set xfer:clobber yes` в lftp, путь `daemon/cottage-monitoring/daemon.lua`.

### TLS к брокеру

- Клиент по умолчанию: `tls_insecure_set(true)` (проверка выкл). Опции `mqtt_tls_verify` / `mqtt_cafile` — opt-in.
- На брокере для LM нужна **короткая** цепочка (2 PEM, issuer R12 / ISRG Root X1). Цепочка YR2 (3 блока) → handshake `protocol error` / unexpected EOF на старом OpenSSL LM.
- Автообновление: certbot `preferred_chain = ISRG Root X1` + deploy-hook `/etc/letsencrypt/renewal-hooks/deploy/10-mosquitto.sh` копирует short-chain в `/etc/mosquitto/certs` и reload mosquitto. Текущий cert (fullchain2) валиден до **2026-08-10**; после renew проверить, что в mosquitto снова 2 блока.
