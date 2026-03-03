# Quickstart: Logic Machine MQTT Client App

**Feature**: 002-logicmachine-mqtt-client  
**Целевая платформа**: LogicMachine controller

---

## Предварительные требования

- LogicMachine с поддержкой Apps и MQTT (mosquitto library)
- **Доступ к контроллеру**: FTP `ftp://apps@192.168.100.130`, рабочая директория `/data/apps/store/data/cottage-monitoring` (SCP не поддерживается)
- MQTT-брокер сервера мониторинга (elion.black-castle.ru:8883, TLS)
- Учётные данные MQTT (логин/пароль) от администратора брокера

---

## Установка

### 1. Копирование файлов на контроллер

Контроллер не поддерживает SCP, используется **lftp** (FTP):

**Вся директория** (с подкаталогами):
```bash
lftp -u apps,<пароль> ftp://192.168.100.130 -e "
cd /data/apps/store/data/cottage-monitoring
lcd cm-client
mirror -R .
bye
"
```

**Один файл** (например, обновлённый daemon):
```bash
lftp -u apps,<пароль> ftp://192.168.100.130 -e "
cd /data/apps/store/data/cottage-monitoring/daemon
lcd cm-client/daemon
put daemon.lua
bye
"
```

**Интерактивно**:
```bash
lftp -u apps,<пароль> ftp://192.168.100.130
cd /data/apps/store/data/cottage-monitoring
lcd cm-client
mirror -R .
# или один файл: cd daemon; put ../daemon/daemon.lua
bye
```

### 2. Установка приложения

В веб-интерфейсе LogicMachine: **Settings → Apps → Install** (если приложение в Dev apps) или копирование в нужную директорию store.

### 3. Регистрация daemon

Daemon автоматически регистрируется при установке приложения. Путь: `/daemon/cottage-monitoring/daemon.lua`.

---

## Настройка

1. Открыть приложение **Cottage Monitoring** в Apps
2. Открыть **Config** (иконка шестерёнки или пункт меню)
3. Заполнить обязательные поля:
   - **house_id**: идентификатор дома (например, `house-01`)
   - **device_id**: идентификатор контроллера (например, `lm-main`)
   - **env_mode**: `prod` (боевой) или `dev` (тестовая среда)
   - **mqtt_host**: `elion.black-castle.ru`
   - **mqtt_port**: `8883`
   - **mqtt_username** / **mqtt_password**: учётные данные MQTT
4. Опционально: debug, buffer_size, snapshot_interval, throttle
5. Нажать **Save**
6. Daemon перезапустится автоматически

---

## Проверка работы

1. **Status**: В списке Apps daemon должен быть запущен (зелёный индикатор)
2. **MQTT**: На сервере мониторинга проверить поступление событий и state
3. **Команды**: Отправить команду через API `POST /api/v1/houses/{house_id}/commands` — свет/обогрев должен среагировать

---

## Ручные действия (index.lp)

- **Выгрузить в файл** — скачивание JSON с meta/objects и текущими значениями
- **Выгрузить в MQTT** — принудительная публикация meta + snapshot (требует подключённый MQTT)

---

## Деплой-скрипты

```bash
./deploy/deploy-lftp.sh 192.168.100.130 apps <пароль>
```

(Скрипт создаётся в Phase 2 — tasks.)
