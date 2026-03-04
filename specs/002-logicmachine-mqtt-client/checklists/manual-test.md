# Manual Test Checklist: Logic Machine MQTT Client

**Feature**: 002-logicmachine-mqtt-client  
**Date**: 2026-03-03

## Prerequisites

- [ ] LogicMachine доступен по FTP `ftp://apps@192.168.100.130`
- [ ] MQTT-брокер сервера (elion.black-castle.ru:8883) доступен
- [ ] Учётные данные MQTT настроены

## 1. Deploy

- [ ] `./deploy/deploy-lftp.sh 192.168.100.130 apps LM_apps123`
- [ ] Файлы скопированы в `/data/apps/store/data/cottage-monitoring`

## 2. Config Form

- [ ] LM → Apps → Install Cottage Monitoring
- [ ] Открыть Config (config-load)
- [ ] Заполнить house_id, device_id, mqtt_host, mqtt_port, mqtt_username, mqtt_password
- [ ] Save (config-save)
- [ ] Daemon перезапустился

## 3. Export to File

- [ ] Открыть приложение
- [ ] Нажать «Выгрузить все объекты в файл»
- [ ] Скачался JSON с ts, schema_hash, count, objects

## 4. Daemon Connect

- [ ] Daemon в статусе Running (зелёный)
- [ ] MQTT подключён (storage.mqtt_connected или по логам)

## 5. Export to MQTT

- [ ] Нажать «Выгрузить все объекты в MQTT»
- [ ] Сообщение «Выгрузка в MQTT запрошена»
- [ ] На сервере получены meta/objects и state/ga/*

## 6. Groupwrite → MQTT

- [ ] Имитировать groupwrite на контроллере (переключить свет/ТП)
- [ ] events в MQTT
- [ ] state/ga/<ga> обновлён в MQTT

## 7. Cmd from API

- [ ] `POST /api/v1/houses/{house_id}/commands` с ga, value
- [ ] Команда выполнена на шине
- [ ] cmd/ack получен с status=ok

## 8. RPC (optional)

- [ ] RPC meta — rpc/req → rpc/resp с meta/objects
- [ ] RPC snapshot — rpc/resp с states
