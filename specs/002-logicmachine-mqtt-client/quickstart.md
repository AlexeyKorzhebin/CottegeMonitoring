# Quickstart: Logic Machine MQTT Client App

**Feature**: 002-logicmachine-mqtt-client  
**Целевая платформа**: LogicMachine controller

---

## Предварительные требования

- LogicMachine с поддержкой Apps и MQTT (mosquitto library)
- **Доступ к контроллеру**: FTP `ftp://apps@192.168.100.130`, рабочая директория `/data/apps/store/data/cottage-monitoring` (SCP не поддерживается)
- **FTP-учётные данные (временный пароль)**: user `apps`, password `LM_apps123`
- MQTT-брокер сервера мониторинга (elion.black-castle.ru:8883, TLS)
- Учётные данные MQTT (логин/пароль) от администратора брокера

---

## Установка

### 1. Копирование файлов на контроллер

Контроллер не поддерживает SCP, используется **lftp** (FTP):

**Рекомендуется** — скрипт деплоя (загружает приложение и daemon):
```bash
./deploy/deploy-lftp.sh 192.168.100.130 apps LM_apps123
```

**Вручную (вся директория)**:
```bash
lftp -u apps,LM_apps123 ftp://192.168.100.130 -e "
cd data/cottage-monitoring
lcd cm-client
mirror -R .
bye
"
```

**Один файл** (например, обновлённый daemon):
```bash
lftp -u apps,LM_apps123 ftp://192.168.100.130 -e "
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

1. **Status**: В списке Apps daemon должен быть запущен (зелёный индикатор)
2. **MQTT**: На сервере мониторинга проверить поступление событий и state
3. **Команды**: Отправить команду через API `POST /api/v1/houses/{house_id}/commands` — свет/обогрев должен среагировать

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
