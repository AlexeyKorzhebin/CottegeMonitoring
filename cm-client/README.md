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
| debug | Включить log/alert |
| snapshot_interval | Периодический snapshot (с), 0 = выкл |
| throttle | Макс. events/с, 0 = без ограничения |
| buffer_size | Размер буфера при offline |

## Установка

### 1. Копирование файлов на контроллер

Контроллер не поддерживает SCP, используется **lftp** (FTP):

```bash
./deploy/deploy-lftp.sh 192.168.100.130 apps LM_apps123
```

Или вручную:
```bash
lftp -u apps,LM_apps123 ftp://192.168.100.130 -e "
cd /data/apps/store/data/cottage-monitoring
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

1. `./deploy/deploy-lftp.sh 192.168.100.130 apps LM_apps123`
2. LM → Apps → Install Cottage Monitoring
3. Config → house_id, device_id, MQTT учётные данные → Save
4. Daemon подключается к MQTT, публикует meta, snapshot, слушает groupwrite
5. **Выгрузить в файл** — JSON с объектами
6. **Выгрузить в MQTT** — принудительная публикация meta+snapshot

## Проверка

- **Status**: Daemon зелёный в Apps
- **Выгрузить в файл** — скачивание JSON
- **Выгрузить в MQTT** — meta + snapshot при подключённом MQTT
