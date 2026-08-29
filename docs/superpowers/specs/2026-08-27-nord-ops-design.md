# Nord Ops — Design Spec

**Date:** 2026-08-27  
**Status:** Draft (awaiting review)  
**Scope:** Единый каталог семантических операций (Ops) и две грани Nord (REST + MCP) без расхождения контракта.  
**Supersedes (частично):** [2026-07-15-mcp-agent-bridge-design.md](./2026-07-15-mcp-agent-bridge-design.md) §3 (intent REST отложен) и §11.2 (ключ навсегда = один скрытый дом). MCP в том же процессе и API-ключ как машина — остаются.  
**Related:** [2026-07-15-house-objects-inventory.md](./2026-07-15-house-objects-inventory.md), `specs/001-server-mqtt-ingestor/contracts/api-v1.md`

---

## 1. Problem

Nord (северный вход: FastAPI на elion) уже отдаёт два протокола из одного процесса: `/api/v1` и `/mcp`. Это не два инстанса. Расхождение в другом.

- REST — ресурсный: дома, объекты, state, команды по групповому адресу.
- MCP — семантический: `set_lights(query, on)` через `agent_actions`.
- Каталога операций нет. Новый kettle появляется в MCP и не появляется как HTTP-операция. Intent REST в спеке 2026-07-15 отложен «пока не понадобится UI» — UI (HA, облачный пульт) понадобился.
- MCP прячет `house_id` внутри ключа. Второй дом = второй ключ и второй агент.
- `GET /api/v1/houses` отдаёт все дома, не гранты ключа. Middleware режет только путь `/houses/{id}`.
- Команда в БД не помнит актора: нельзя отличить Telegram от будущего HA.

Клиенты (Telegram, будущий HA, будущий веб) должны вызывать **одни и те же функции**. Грани не должны жить своей жизнью.

## 2. Vocabulary (обязательный)

| Термин | Значение |
|--------|----------|
| **Nord** | Северный вход. Один процесс на elion: авторизация, Ops, ресурсный REST, ingest MQTT → БД. Клиенты ходят только сюда. |
| **Ops** | Каталог семантических операций (`list_lights`, `set_climate`, …). Единственный источник контракта. |
| **REST-грань** | HTTP JSON поверх Ops (`/api/v1/.../ops/...`) плюс уже существующий ресурсный REST по GA. |
| **MCP-грань** | MCP tools поверх тех же Ops. `/mcp` в том же uvicorn. Не отдельный сервис. |
| **Ресурсный REST** | `objects`, `state`, `events`, `commands` по GA. Для отладки и адаптеров, которым нужна схема. В MCP **не** проецируется. |
| **Principal** | Кто вызывает: сейчас только API-ключ (машина). Человек/JWT — позже, тот же authorize(). |
| **Grant** | Principal × дом. Сейчас одна колонка `api_keys.house_id`. Контекст уже `house_ids: frozenset`. |
| **Наблюдатель** | Grafana. Только SELECT по БД, которую наполняет Nord. Не грань Nord, не `POST /commands`, не MQTT. |
| **Mosaic** | Локальный UI LogicMachine. Не Nord. |

Говорим: «ставим HA на Nord», «расширяем Ops», «MCP-грань». Не говорим «MCP-сервер» как отдельный деплой.

## 3. Goals

| Goal | Decision |
|------|----------|
| Один каталог | Ops регистрируется один раз; REST-грань и MCP-грань строятся из записи |
| Ноль расхождения | Тест: множество имён MCP tools (ops) == реестр == `GET /ops`. Вызов REST и MCP бьёт в один и тот же handler |
| Тот же процесс | `/mcp` остаётся mount в FastAPI. Sidecar запрещён |
| Дом в контракте | House-scoped Op всегда имеет `house_id`. MCP может опустить его, только если грант ровно один |
| Клиенты равны | Telegram (MCP) и HA/веб (REST) — грани одних Ops |
| OpenClaw skill | Тот же контракт Ops: `skills/cottage-monitoring/` обновляется в этой же фиче, не «потом» |
| Актор | Команда в БД помнит `actor_key_id` |
| Список домов | `GET /houses` и MCP `list_houses` — одна функция, только гранты principal |

## 4. Non-goals (этой спеки)

- Деплой Home Assistant на elion, MQTT Discovery, KNX-туннель HA → LM.
- Таблица `users`, OAuth/JWT, роли на комнаты, junction `api_key_houses` (много домов на ключ в БД).
- Генерация MCP из OpenAPI ресурсного REST (это вытащило бы GA в агента).
- Перенос автоматизаций/сцен в Nord или HA. Мозг дома — LogicMachine.
- Grafana как HTTP-клиент Nord; панели остаются SQL по Timescale.
- Изменение MQTT-протокола `cm/.../v1`.
- Переписывание `agent_actions` с нуля: функции остаются handlers.

## 5. Approaches considered

| Подход | Суть | Почему нет / да |
|--------|------|-----------------|
| A. Sidecar MCP | Отдельный процесс | Уже отвергнут 2026-07-15. Двойной деплой, два места менять контракт |
| B. MCP из OpenAPI ресурсного REST | Автогенерация tools по GA API | Агенту не нужны сырые адреса; «автоподхват» чужого контракта |
| **C. Реестр Ops (выбран)** | Одна регистрация → две грани | Ноль ручных параллельных колонок; UI и бот не разъезжаются |

## 6. Architecture

```text
Telegram / OpenClaw          HA / веб / Алиса           Grafana
        │ MCP-грань                 │ REST-грань            │ SELECT
        ▼                           ▼                       ▼
┌─────────────────────────────────────────────┐      PostgreSQL
│  Nord  (один FastAPI / uvicorn)             │      Timescale
│                                             │           ▲
│  authorize(principal, house_id, perm)       │           │
│  Ops registry  ──генерит──► MCP tools       │           │
│       └──генерит──► POST .../ops/{name}     │           │
│  handlers = agent_actions.*                 │           │
│  resource REST (GA) — отдельно, не в MCP    │           │
│  ingest MQTT → DB / Redis                   ┼───────────┘
└──────────────────────┬──────────────────────┘
                       │ MQTT cm/.../v1/cmd
                       ▼
                 LogicMachine → KNX
```

Mosaic на контроллере в эту схему не входит.

## 7. Ops registry

Одна запись на операцию. Ни `@mcp.tool` в обход реестра, ни ручной FastAPI-роут для той же семантики.

```text
OpSpec:
  name: str                 # каноническое имя, = MCP tool name
  permission: "read"|"write"
  house_scoped: bool        # false только у list_houses
  description: str          # одна строка на обе грани
  handler: callable         # async (session, house_id?, **params) → dict
```

Параметры (кроме `session` и `house_id`) описываются одной Pydantic-моделью на Op. Из неё:

- JSON Schema MCP tool
- тело `POST /ops/{name}`
- OpenAPI

Имя MCP tool **равно** `OpSpec.name` **равно** сегменту URL.

Диспетчер (общий для обеих граней):

1. Найти Op по имени. Нет — 404.
2. Проверить `permission` против `principal.scopes` (`read`/`write` как сейчас). Нет — 403.
3. Если `house_scoped`: резолв `house_id` (см. §9), `authorize(principal, house_id, permission)`, передать `house_id` в handler. Если нет — `house_id` в handler не передаётся (`list_houses` фильтрует по `ctx.house_ids` сам).
4. Если `write`: существующий write rate-limit по `principal_id` (сейчас он только в MCP — должен срабатывать и на REST-грани).
5. Вызвать `handler`. Ошибки `HTTPException` мапятся: REST — как сейчас; MCP — JSON `{status, code, error}` как сейчас.

Запрещено вызывать `command_service` / MQTT из кода грани. Только handler.

## 8. REST-грань Ops

Чтобы не плодить GET-vs-POST и не разъехаться с MCP (все tools — RPC), **все Ops вызываются POST**, включая чтение.

| Метод | Путь | Назначение |
|-------|------|------------|
| `GET` | `/api/v1/ops` | Каталог: ops, которые позволяет scope ключа (без write-операций для read-only) |
| `POST` | `/api/v1/houses/{house_id}/ops/{name}` | Только house-scoped Op. Тело — JSON параметров **без** `house_id` |
| `GET` | `/api/v1/houses` | REST-binding единственного не-house-scoped Op `list_houses`. Тот же handler, что MCP-tool. Отдельного `POST /ops/list_houses` нет |

Тело запроса = поля Pydantic-модели Op. Ответ 200 = тот же `dict`, что handler (и что MCP сериализует в JSON-строку tool result).

`X-Cottage-Dry-Run` на write Ops работает как на текущем `POST /commands`.

Ресурсный REST (`GET .../state`, `POST .../commands` по GA и т.д.) **не удаляем**. HA может читать схему/state оттуда и слать семантику через Ops — или слать GA-команды. Оба пути идут в `command_service`.

## 9. MCP-грань и дом

Существующие tool names сохраняются. Добавляется `list_houses`.

У каждого house-scoped tool появляется опциональный аргумент `house_id: str | None = None`.

Резолв:

| Гранты principal | `house_id` в вызове | Результат |
|------------------|---------------------|-----------|
| ровно 1 | опущен | подставить этот дом (совместимость Telegram) |
| ровно 1 | передан и совпал | ок |
| ровно 1 | передан и другой | 403 |
| 0 | любой | 403 |
| >1 | опущен | 400, `"house_id required"` — не выбирать первый |
| >1 | передан и в грантах | ок |
| >1 | передан и не в грантах | 403 |

Это то же правило, что у `discover`: при неоднозначности не угадывать.

В этой спеке в БД по-прежнему один `api_keys.house_id`. Ветки «>1 грант» обязаны быть в коде резолва и покрыты тестами (контекст с двумя id), даже если CLI ключа ещё не умеет выдать два дома.

## 10. Principal и authorize

Заменить смысл `ApiKeyContext.house_id: str` на гранты.

```text
ApiKeyContext:
  key_id: UUID
  name: str
  scopes: frozenset[str]          # "read", "write"
  house_ids: frozenset[str]
```

Хелпер: `default_house_id() -> str | None` — единственный элемент либо `None`.

`authorize(ctx, house_id, permission)` — единственная проверка «дом ∈ house_ids» и scope. Её зовут:

- диспетчер Ops
- middleware на `/api/v1/houses/{house_id}/...` (вместо `!= ctx.house_id`)
- ресурсный REST, если не закрыт middleware

`GET /api/v1/houses` фильтрует `House.house_id IN ctx.house_ids`. При `AUTH_REQUIRED=false` (dev/test) — как сейчас, все дома.

Роли viewer/operator/admin и таблица users **не вводятся**. Mapping на будущее: `read` → viewer, `write` → operator. `principal_kind` в коде можно завести константой `"api_key"`, без таблицы.

## 11. Актор команды

В `commands` добавить nullable `actor_key_id UUID` (FK на `api_keys.id`).

Диспетчер write-Op и существующий `POST /commands` проставляют `actor_key_id = ctx.key_id`, когда контекст есть. Dev без auth — NULL.

Комментарий в payload (`mcp set_lights …`) можно оставить; колонка — источник истины для «кто».

## 12. Начальный каталог Ops

Перенос существующих MCP tools 1:1. Handler — текущие функции `agent_actions` (для климата handler остаётся `set_climate_setpoint`, **имя Op** — `set_climate`, как tool сейчас).

| name | permission | house_scoped | handler сегодня |
|------|------------|--------------|-----------------|
| `list_houses` | read | нет | новая тонкая обёртка над выборкой домов по грантам; её же зовёт `GET /houses` |
| `get_house_status` | read | да | `get_house_status` |
| `discover` | read | да | `discover` |
| `get_temperature` | read | да | `get_temperatures` |
| `get_sensors` | read | да | `get_sensors` |
| `list_lights` | read | да | `list_lights` |
| `set_light` | write | да | `set_light` |
| `set_lights` | write | да | `set_lights` |
| `set_commands` | write | да | `set_commands` |
| `get_climate` | read | да | `get_climate` |
| `set_climate` | write | да | `set_climate_setpoint` |
| `get_energy_status` | read | да | `get_energy_status` |
| `get_heating_diagnostics` | read | да | `get_heating_diagnostics` |
| `get_kettle` | read | да | `get_kettle` |
| `set_kettle` | write | да | `set_kettle` |
| `get_command_status` | read | да | `get_command_status` |

Новая семантика (ещё один прибор) = новая запись в реестре. Запрещено добавить `@mcp.tool` без записи. Тест это ловит.

## 13. Grafana, Mosaic, HA (границы)

**Grafana.** Наблюдатель склада Nord. Спека не меняет дашборды. Запрещено добавлять из Grafana путь в `command_service` или в брокер.

**Mosaic.** LAN, LogicMachine. Вне Nord.

**Home Assistant.** Целевой клиент REST-грани (ресурсный слой для схемы/state + Ops для семантики). Деплой контейнера, nginx-поддомен, MQTT user для HA — **следующая спека**. Эта спека обязана дать контракт, которым HA сможет пользоваться: каталог `GET /ops`, `POST .../ops/{name}`, ключ operator на один дом.

HA не получает MQTT ACL на `cm/#`.

## 14. Compatibility

- OpenClaw / skill: без `house_id` на tools работает, пока ключ однодомный. Точные правки — §19, не сноска.
- Имена tools не переименовывать.
- Ресурсный `/api/v1` по GA не ломать.
- JSON ошибок MCP (`status`, `code`, `error`) сохранить.

## 15. Testing

Обязательные тесты (без живого MQTT, где возможно):

1. **Drift names:** `set(registry.names) == set(mcp tool names) == set(GET /ops names для ключа write)`. Read-only ключ: `/ops` без write-имён.
2. **Drift handler:** REST `POST .../ops/list_lights` и MCP `list_lights` вызывают один и тот же callable (мокнутый registry/spy).
3. **No rogue tools:** в `mcp.list_tools()` нет имён вне реестра.
4. **House resolve:** однодомный ключ без аргумента; двудомный контекст без аргумента → 400; чужой дом → 403.
5. **GET /houses** при auth отдаёт только `house_ids` ключа, не все ряды `houses`.
6. **Write rate-limit** срабатывает на REST `POST .../ops/set_light`, не только на MCP.
7. **actor_key_id** пишется при write Op (можно command_service + dry-run).
8. Существующие unit MCP (`test_mcp_tools.py`) переводятся на реестр, без второго хардкода списка в тесте «ожидаемые имена» vs «ожидаемые имена в server.py».
9. **Skill:** в `SKILL.md` есть `list_houses` и правила `house_id` из §19 (проверка grep/содержимого в CI или в checklist плана — skill не должен описывать tools, которых нет в реестре).

## 16. Risks

| Risk | Mitigation |
|------|------------|
| POST на read Ops непривычен | Документировать как RPC-грань; цена — ноль GET/POST маппинга |
| `agent_actions.py` большой | Не дробить в этой спеке; реестр только указывает на функции |
| OpenClaw сломается на новом обязательном house_id | Аргумент optional; обязателен только при >1 гранте |
| GET /houses меняет поведение (перестанет отдавать чужие дома) | Это исправление утечки; в dev без auth — без изменений |

## 17. Success criteria

1. Нельзя добавить семантику в одну грань, не попав в другую: реестр + drift-тест.
2. Telegram с однодомным ключом работает как сейчас; skill OpenClaw описывает новый контракт (§19).
3. HA (когда появится) может вызвать ту же `set_lights`, что бот, через REST.
4. Дом в контракте Ops и MCP; список домов = гранты.
5. Grafana по-прежнему не шлёт команды.
6. Один процесс Nord.

## 18. Implementation order (для плана, не код)

1. `ApiKeyContext.house_ids` + `authorize()` + фильтр `GET /houses` + middleware.
2. Реестр Ops + диспетчер.
3. Перенос MCP tools на реестр; `list_houses`; optional `house_id`.
4. REST `GET /ops` + `POST .../ops/{name}`; rate-limit в диспетчере.
5. `commands.actor_key_id`.
6. Drift-тесты.
7. Skill OpenClaw и связанные инструкции (§19) — тот же PR, что реестр. Не отдельный «документационный хвост».
8. Короткая запись в `specs/001-server-mqtt-ingestor/research.md` (R-xxx).

Деплой HA — не в этом порядке.

## 19. OpenClaw skill (обязательный deliverable)

MCP-грань без skill — сломанный Telegram: агент не знает `list_houses`, будет угадывать дом или звать несуществующий CLI. Skill обновляется **в том же изменении**, что реестр Ops, не отдельным коммитом «доки потом».

### Файлы в репозитории

| Файл | Что менять |
|------|------------|
| `skills/cottage-monitoring/SKILL.md` | Канон routing/tools/дом для агента |
| `skills/cottage-monitoring/references/openclaw-connection.md` | Probe: 16 tools; native MCP |
| `specs/001-server-mqtt-ingestor/openclaw-cottage-agent-instructions.md` | Канон `AGENTS.md` + rsync; держать в синхроне со live |

### Live на elion (проверено SSH 2026-08-27)

Агент `cottage` в `openclaw.json`: `workspace=/home/openclaw/.openclaw/workspace-cottage`, `skills=["cottage-monitoring"]`, tools `minimal` + `alsoAllow: ["bundle-mcp"]`.

| Путь | Роль |
|------|------|
| `/home/openclaw/.openclaw/workspace-cottage/AGENTS.md` | Bootstrap агента. **Файл есть**, совпадает с каноном в `openclaw-cottage-agent-instructions.md`. Routing ladder; запрет `exec`/`mcporter`. Сюда же — `list_houses` / `house_id`. |
| `/home/openclaw/.openclaw/workspace/skills/cottage-monitoring/` | Единственная копия skill (`SKILL.md` + `references/`). `skills.entries.cottage-monitoring.enabled=true`. |
| `/home/openclaw/.openclaw/workspace-cottage/skills/cottage-monitoring` | **Симлинк** на `workspace/skills/cottage-monitoring`. Копировать skill во второй раз не нужно. |
| `/home/openclaw/.openclaw/workspace-cottage/TOOLS.md` | Bootstrap tools. Канон `openclaw-cottage-tools.md` — native MCP (`cottage__*`), не `mcporter call`. Follow-up #4: [2026-08-29-openclaw-tools-md-design.md](./2026-08-29-openclaw-tools-md-design.md). |
| `SOUL.md` / `IDENTITY.md` / `USER.md` / `HEARTBEAT.md` | Короткие; к контракту Ops не относятся. Не трогать без нужды. |
| `/home/openclaw/.openclaw/agents/cottage/` | Только sessions. `agentDir` из json (`.../agent`) на диске **нет**. |

Репозиторный `SKILL.md` чуть впереди live (на elion нет фразы про skip/`1/2/*` у `set_lights`). При выкладке skill на elion подтянуть целиком.

Расхождение skill ↔ реестр Ops = баг фичи. Расхождение репо-канона `AGENTS.md` ↔ файл в `workspace-cottage` = баг выкладки.

### Обязательное содержание SKILL.md **и** live `AGENTS.md`

Оба читаются агентом (skill через OpenClaw skills, `AGENTS.md` как workspace bootstrap). Правила дома дублировать в обоих, иначе Flash увидит только одно.

1. **Словарь.** OpenClaw ходит в **MCP-грань Nord** (`http://127.0.0.1:8321/mcp`), не в «отдельный MCP-сервер» и не в REST-грань. Grafana/Mosaic не вызывать.
2. **`list_houses`.** Строка в таблице Tool selection: «какой дом / список домов» → `list_houses`. В routing ladder — перед house-scoped tools, если домов может быть больше одного.
3. **`house_id`.** У house-scoped tools аргумент опциональный.
   - `list_houses` вернул один дом (или ключ однодомный) — **не** передавать `house_id` (совместимость как сейчас).
   - Вернул больше одного — каждый последующий tool **с** `house_id`. Не выбирать первый дом молча. Если пользователь не назвал дом — спросить.
   - Чужой / неизвестный дом — не выдумывать; опереться на ответ 403.
4. **Имена tools** те же (`cottage__set_lights` и т.д.). Новые tools кроме `list_houses` не добавлять в skill, пока их нет в реестре.
5. Старые запреты сохранить: нет `exec`, нет `mcporter list` / `list-commands`, зона света → один `set_lights`, чайник не искать среди ламп, heating rules без изменений.
6. Ключ — машина с грантами на дом(а), scopes `read`/`write`. Не описывать пользовательский логин.
7. REST `POST /ops/{name}` в skill **не** учить агента: Telegram остаётся на MCP-грани.

### openclaw-connection.md

- `openclaw mcp probe cottage`: ожидать **16** house tools (было 15), в том числе `list_houses`.
- Smoke: однодомный ключ — `cottage__get_house_status` **без** `house_id`.

### Что не делать до появления tool на prod

Не класть в live `AGENTS.md` / skill вызов `list_houses`, пока Nord на elion ещё на старом MCP.

Порядок выкладки (один заход после образа с реестром):

1. Skill → `/home/openclaw/.openclaw/workspace/skills/cottage-monitoring/` (симлинк из cottage workspace). Предпочтительно `openclaw skills install <repo>/skills/cottage-monitoring --agent cottage --force`, если CLI в PATH.
2. Обновить `/home/openclaw/.openclaw/workspace-cottage/AGENTS.md` из канона в `openclaw-cottage-agent-instructions.md`.
3. Обновить `TOOLS.md` из `openclaw-cottage-tools.md`.
4. `openclaw mcp probe cottage` — 17 tools. Текущий Telegram-чат: `/new` или перечитать AGENTS.

Skill и AGENTS.md держать короткими (routing, не JSON-схемы). Схемы уже в MCP `tools/list`. Сверка каталога для оператора: `cottage-ops catalog` (тот же реестр Ops).

`TOOLS.md` — native MCP, канон `openclaw-cottage-tools.md` (issue #4, 2026-08-29).

## 20. Follow-up (не эта спека)

- **OpenClaw `TOOLS.md` vs `AGENTS.md`:** сделано 2026-08-29 — [2026-08-29-openclaw-tools-md-design.md](./2026-08-29-openclaw-tools-md-design.md), issue #4.
- **MCP не stateless 2026-07-28.** Оставлено как есть 2026-08-29 (R-028): пин `mcp>=1.0,<2`, FastMCP + `session_manager`. Не апгрейдить, пока OpenClaw на elion не заговорит 2026-07-28 без фолбэка, не появятся реплики Nord или CVE без патча 1.x. https://github.com/AlexeyKorzhebin/CottegeMonitoring/issues/5
- Деплой Home Assistant на Nord — отдельная спека.
