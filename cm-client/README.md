# Cottage Monitoring — Logic Machine MQTT Client

Клиентское приложение для контроллера LogicMachine. Публикует телеметрию (events, state, meta) в MQTT-брокер сервера мониторинга, получает команды, поддерживает RPC.

## Поля конфигурации

| Поле | Описание |
|------|----------|
| house_id | ID дома (1–64 символа) |
| device_id | ID контроллера |
| env_mode | `prod` или `dev` (префикс топиков) |
| mqtt_host | Хост брокера (напр. elion.black-castle.ru) |
| mqtt_port | Порт (8883 для TLS) |
| mqtt_username, mqtt_password | Учётные данные MQTT |
| mqtt_use_tls | TLS (всегда включён) |
| client_id | Опционально (по умолчанию house_id-device_id) |
| debug_level | 0=выкл, 1=логи сброса буфера, 2=все отладочные логи |
| batch_interval | Интервал отправки буфера (с), 0 = немедленно (default 1.5) |
| batch_max_size | Сброс буфера при достижении размера, 0 = без лимита (default 50) |
| snapshot_interval | Периодический snapshot (с), 0 = выкл |
| throttle | Макс. events/с, 0 = без ограничения (default 20) |
| buffer_size | Размер буфера при offline |
| event_sleep | Пауза после KNX-события (с), default 0.03 |
| loop_sleep | Пауза главного цикла (с), default 0.25 |

## Установка

### 1. Копирование файлов на контроллер

Контроллер не поддерживает SCP, используется **lftp** (FTP).

Пароли — в локальном `secrets/lm.env` (не в git; шаблон `secrets/lm.env.example`):

```bash
cp secrets/lm.env.example secrets/lm.env   # один раз, заполнить пароли
./deploy/deploy-lftp.sh                    # без пароля в командной строке
./deploy/lm-apps.sh pause-wd
./deploy/lm-apps.sh stop                   # затем upload, затем:
./deploy/lm-apps.sh start
./deploy/lm-apps.sh health
```

Учётки контроллера (LAN): FTP `apps`, веб `admin` — значения паролей только в `secrets/lm.env`.

Или вручную (пароль из env после `source secrets/lm.env`):
```bash
lftp -u "$LM_FTP_USER","$LM_FTP_PASSWORD" "ftp://$LM_HOST" -e "
cd data/cottage-monitoring
lcd cm-client
mirror -R .
bye
"
```

### 2. Установка приложения

В веб-интерфейсе LogicMachine: **Settings → Apps → Install**.

### 3. Регистрация daemon

Daemon автоматически регистрируется. Путь: `/daemon/cottage-monitoring/daemon.lua`.

## Настройка

1. Открыть приложение **Cottage Monitoring** в Apps
2. Открыть **Config**
3. Заполнить house_id, device_id, mqtt_host, mqtt_port, mqtt_username, mqtt_password
4. Нажать **Save** — daemon перезапустится

## Quickstart

1. `./deploy/deploy-lftp.sh` (пароли из `secrets/lm.env`)
2. LM → Apps → Install Cottage Monitoring
3. Config → house_id, device_id, MQTT учётные данные → Save
4. Daemon подключается к MQTT, публикует meta, snapshot, слушает groupwrite
5. **Выгрузить в файл** — JSON с объектами
6. **Выгрузить в MQTT** — принудительная публикация meta+snapshot

## Надёжность (v1.1)

- **Reconnect с backoff**: при обрыве MQTT daemon повторяет `reconnect`/`connect` с задержкой 2→60 с (не одноразовая попытка).
- **Проверка `loop()`**: ненулевой код → помечает соединение разорванным.
- **pcall** вокруг connect и тела главного цикла — ошибка итерации не убивает daemon.
- **Heartbeat**: `storage.cm_heartbeat` каждый цикл; при долгом offline (>300 с) — пересоздание MQTT-клиента.
- **Watchdog (Resident)**: `scripts/watchdog-resident.lua` — soft → hard. Для hard HTTP-рестарта один раз на LM (Scripting console):
  `config.set('cottage-monitoring', 'lm_admin_password', '…')` — пароль не в git. Перед деплоем daemon: `./deploy/lm-apps.sh pause-wd`.
- **Диагностика**: UI + `health_get.lp` + retained `…/v1/status/health`.
- **MQTT loop**: всегда вызывать `loop()` (и offline); ошибка loop — только numeric `rc ~= 0` (иначе reconnect-storm на LM).
- **Деплой daemon**: FTP `daemon/cottage-monitoring/daemon.lua`, цикл stop→put→start.

### Установка watchdog

1. LM → **Scripting** → **Resident** → Add
2. Name: `CM watchdog`, Sleep: `60`, Active: on
3. Вставить содержимое `cm-client/scripts/watchdog-resident.lua`
4. Save

## Проверка

- **Status**: Daemon зелёный в Apps
- **Диагностика** в UI: MQTT online, heartbeat age, reconnects
- **Выгрузить в файл** — скачивание JSON
- **Выгрузить в MQTT** — meta + snapshot при подключённом MQTT
