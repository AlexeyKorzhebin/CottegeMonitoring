# OpenClaw cottage TOOLS.md — native MCP

**Date:** 2026-08-29  
**Status:** Implemented  
**Issue:** [#4](https://github.com/AlexeyKorzhebin/CottegeMonitoring/issues/4)  
**Depends on:** [2026-08-27-nord-ops-design.md](./2026-08-27-nord-ops-design.md) §20  
**Out of scope:** MCP SDK 2.x / issue #5.

---

## Problem

OpenClaw подмешивает `TOOLS.md` в bootstrap агента `cottage`. Live файл учил `mcporter call cottage.get_house_status`. `AGENTS.md` и skill запрещают `exec` / `mcporter`. Модель читает оба и снова лезет в CLI → `Exec failed` в Telegram.

## Decision

Не удалять `TOOLS.md` (OpenClaw может снова сгенерировать CLI-шпаргалку). Переписать под native MCP, в одном духе с `AGENTS.md`. mcporter — одна строка: шелл/бенчи, не путь агента.

Канон в репо: `specs/001-server-mqtt-ingestor/openclaw-cottage-tools.md`. Выкладка: скопировать в `/home/openclaw/.openclaw/workspace-cottage/TOOLS.md`. Nord / каталог Ops / образ не трогать.

## Success

- Live `TOOLS.md` не содержит `mcporter call cottage.` как инструкцию агента.
- Есть `cottage__` и запрет `exec` / `mcporter` / `list-commands`.
- Drift-тест канона в `test_ops_cli.py`.
- Smoke агента зовёт native MCP, не exec.
