# Implementation Plan: Logic Machine MQTT Client App

**Branch**: `002-logicmachine-mqtt-client` | **Date**: 2026-03-03 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/002-logicmachine-mqtt-client/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command.

## Summary

Клиентское приложение для контроллера LogicMachine: daemon (Lua) + веб-интерфейс (config.lp/index.lp). Подключается к MQTT-брокеру сервера мониторинга, публикует телеметрию (events, state, meta), получает команды, поддерживает RPC (meta/snapshot). Настройки через веб-форму (config.get/set). Использует LogicMachine API: mosquitto (MQTT), localbus (groupwrite), grp, json, config.

## Technical Context

**Language/Version**: Lua 5.1 (embedded in LogicMachine)  
**Primary Dependencies**: mosquitto (MQTT client), localbus (KNX events), grp (objects), json, config, encdec (SHA256 для schema_hash)  
**Storage**: config.get/set для настроек; storage — опционально для буфера (предпочтительно RAM)  
**Testing**: Ручное тестирование на LogicMachine; интеграция с сервером spec 001  
**Target Platform**: LogicMachine controller (embedded Linux, Lua 5.1)  
**Project Type**: Logic Machine App (daemon + web config UI)  
**Performance Goals**: События в облако <2 c; команда выполнена <3 c; meta ~150 объектов за <30 c  
**Constraints**: TLS обязателен; alert/log через config.debug; ограниченная память контроллера  
**Scale/Scope**: ~150 KNX объектов на контроллер; буфер до 2000 записей при offline

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Notes |
|------|--------|-------|
| Архитектура (облако + контроллер) | ✓ | Клиент — часть локальной подсистемы |
| Отдельные тесты для контроллера | ✓ | Ручные тест-кейсы по quickstart + acceptance scenarios (Principle V: LM не поддерживает autom. test runner; чеклист в tasks T034) |
| База данных PostgreSQL + TimescaleDB | N/A | Контроллер не пишет в БД |

## Project Structure

### Documentation (this feature)

```text
specs/002-logicmachine-mqtt-client/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
cm-client/                    # Logic Machine App (деплой: lftp/FTP в /data/apps/store/data/cottage-monitoring)
├── config.lp                 # Форма настроек (config-load, config-check, config-save)
├── index.lp                  # Главная страница приложения
├── icon.svg                  # Иконка приложения
├── daemon/
│   └── daemon.lua            # MQTT клиент, localbus listener, cmd executor
├── libs/                     # Опционально для выноса модулей (не в scope MVP)
└── README.md                 # Инструкция по установке

deploy/
└── deploy-lftp.sh           # lftp-деплой на контроллер (SCP не поддерживается)
```

**Structure Decision**: Logic Machine App по [kb.logicmachine.net/misc/apps/](https://kb.logicmachine.net/misc/apps/): daemon в `/daemon/<appname>/daemon.lua`, конфиг в `config.lp`, UI в `index.lp`. Исходники в `cm-client/`; на контроллер — `/data/apps/store/data/cottage-monitoring/`.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
