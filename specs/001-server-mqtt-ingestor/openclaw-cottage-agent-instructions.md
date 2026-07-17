# OpenClaw: агент `cottage` (быстрый дом)

Спека: [research.md](./research.md) **R-014**, dry-run **R-013**. Skill: `skills/cottage-monitoring/`.

## Статус (live, 2026-07-17)

На elion уже работает:

| Параметр | Значение |
|----------|----------|
| Agent id | `cottage` |
| Model | `caila/just-ai/google-gemini/gemini-3.5-flash` (`thinkingDefault=low`) |
| Fallback | `caila/just-ai/anthropic-claude/claude-haiku-4-5` |
| Workspace | `/home/openclaw/.openclaw/workspace-cottage/` |
| Skill | только `cottage-monitoring` |
| Telegram | топик «🏡 Усадьба» → binding на `cottage` |
| MCP | mcporter alias `cottage` → `http://127.0.0.1:8321/mcp` |
| Dry-run тесты | alias `cottage-dry` + header `X-Cottage-Dry-Run` |

`AGENTS.md` и skill лежат на диске и подхватываются на каждом run — **не нужно** повторять routing-инструкцию в каждой сессии. Разовое «перечитай AGENTS» — только после правки файлов, чтобы текущий чат сразу подхватил изменения.

`memorySearch` у cottage выключен (долгая память). История **диалога в топике** сохраняется: follow-up вроде «увеличь его яркость» после «включи свет на кухне» резолвится из session history.

---

## Почему не `mcporter list` / `list-commands`

1. Каталог tools уже в skill — лишний ход и задержка.
2. Модель часто ломает синтаксис (`list-commands` как «сервер» → `Unknown MCP server`).
3. После ошибки семантического tool нужен `set_kettle` / `discover`, а не «покажи все команды».

---

## Routing ladder (канон)

Порядок сверху вниз:

1. **Семантический tool** — свет зона/этаж → `set_lights`; лампа/торшер → `set_light`; чайник → `set_kettle`/`get_kettle`; ТП → `set_climate`; отчёт/энергия → `get_*`.
2. **Имя без зоны** (торшер, подсветка стола) → `set_light` / `discover` с query.
3. **Неизвестный прибор** → `discover(query, kind=all|appliance)` → act или уточнение при `ambiguous`.
4. Не искать чайник среди ламп. Не вызывать `mcporter list` / `list-commands` перед действием.

---

## Проверенные примеры (Telegram «Усадьба»)

### Свет

| Пользователь | Ожидаемый tool | Результат |
|--------------|----------------|-----------|
| включи свет на первом этаже | `set_lights` zone/floor | 9 групп (после подтверждения live, если агент спросил) |
| включи свет на 2 этаже | `set_lights` | 8 групп |
| выключи свет на 2 этаже | `set_lights` on=false | выключен |
| включи торшер и подсветку стола | `set_light` ×2 (по имени) | торшер гостиная + подсветка кухня |

### Чайник и энергия

| Пользователь | Tool | Пример ответа |
|--------------|------|---------------|
| включи чайник | `set_kettle` | Чайник успешно включен |
| скажи температуру чайника | `get_kettle` | … 36 °C |
| выключи чайник | `set_kettle` | выключен |
| какое сейчас потребление энергии по фазам? | `get_energy_status` | Вт/А/В по фазам + сумма + кВт·ч за день |

### Follow-up / история

| Ход 1 | Ход 2 | Поведение |
|-------|-------|-----------|
| включи свет на первом этаже | подтверждаю | продолжает ту же команду |
| выключи свет на 2 этаже (агент: уже выключен) | он был включен, выключи | повторный `set_lights` force |

Местоимения («его яркость») работают **внутри той же session/топика**. После `/new` или сброса сессии — нет.

---

## Канонический `AGENTS.md` (workspace-cottage)

Синхронизировать с live на elion при правках:

```markdown
# AGENTS.md — cottage

Ты агент управления дачей через CottageMonitoring MCP (`mcporter` alias `cottage`).

## Routing ladder (обязательно)

1. Семантический tool, если интент ясен:
   - зона/этаж/улица света → `set_lights` (не цикл `set_light`)
   - одна лампа / торшер / подсветка по имени → `set_light`
   - чайник / teapot / Redmond → `set_kettle` / `get_kettle` (НЕ искать среди ламп, НЕ set_lights)
   - уставка ТП → `set_climate(setpoint_c)` без `force_relay`
   - отчёт / энергия / климат read → `get_house_status` / `get_energy_status` / `get_climate` / `get_temperature`
2. Имя устройства без зоны → сразу `set_light` или `discover` с этим query.
3. Неизвестный прибор (не свет/климат/чайник) → `discover(query="<имя>", kind="all")` (или kind=appliance).
   - нашёл однозначный control → действуй (`set_light` / `set_commands` с ga+value)
   - ambiguous → спроси, покажи кандидатов
   - пусто → скажи «не нашёл», не выдумывай GA
4. НЕ вызывай `mcporter list` / `list-commands` перед действием — tools уже известны из skill.

## Правила

- Отвечай кратко. Tools только; не выдумывай GA.
- «весь свет» без этажа/зоны → уточни или зоны «1 этаж» / «2 этаж» / «уличное».
- Не трогай авто-балансировку отопления без явной просьбы.
- Не делать web/research и не ходить в main memory.
- Явная команда пользователя («включи», «выключи», «установи») — сразу production alias `cottage`, без dry-run и без лишнего подтверждения.
- Alias `cottage-dry` — только если пользователь прямо попросил dry-run/тест.
- Уточняй только при ambiguous / потенциально опасной команде.
```

После правки на машине разработки:

```bash
rsync -az skills/cottage-monitoring/ elion:/tmp/cottage-monitoring-skill/
# затем на elion: sudo rsync в workspace и workspace-cottage + chown openclaw
```

---

## Восстановление с нуля (вставить Элиону)

Нужно только если агент/workspace пропали. Скопируй блок:

```text
Задача: завести отдельного агента для управления дачей через CottageMonitoring MCP.
Цель — быстрые dial-команды без огромного контекста main и без gpt-5.6-sol.

Контекст (R-014):
- Узкое место — LLM + большой контекст main, не MQTT/MCP (~1 с).
- gemini-3.5-flash ≈ 2× быстрее sol на коротком промпте; с min context обычно ≥2×.
- Skill: ~/.openclaw/workspace/skills/cottage-monitoring/ (и копия в workspace-cottage).
- MCP: mcporter alias `cottage` → http://127.0.0.1:8321/mcp.
- Для тестов write без MQTT: cottage-dry (X-Cottage-Dry-Run).

Сделай на elion:

1) Модель Flash в openclaw.json + thinking/reasoning/thinking_level = low.
   Fallback: caila/just-ai/anthropic-claude/claude-haiku-4-5.

2) openclaw agents add cottage \
     --workspace /home/openclaw/.openclaw/workspace-cottage \
     --model caila/just-ai/google-gemini/gemini-3.5-flash \
     --non-interactive
   skills = только ["cottage-monitoring"]; heartbeat off; memorySearch disabled;
   thinkingDefault = "low".

3) workspace-cottage: skill + AGENTS.md из спеки openclaw-cottage-agent-instructions.md
   (канон выше). НЕ копировать MEMORY/SOUL/HEARTBEAT из main.

4) Telegram topic «Усадьба» → agentId cottage. main остаётся на sol.

5) Smoke: отчёт по дому; свет на этаже; включи чайник → set_kettle;
   температура чайника; энергия по фазам. Не вызывай mcporter list/list-commands.

6) Не меняй primary model main на Flash. Backup openclaw.json. validate + gateway restart.
```

---

## Связанные артефакты

- Бенч моделей: `server/scripts/bench_mcp_models/`
- Image pin dry-run: `cottage-monitoring:0.2.6` (`server/deploy/IMAGE_PIN.yaml`)
- Skill routing: `skills/cottage-monitoring/SKILL.md`
