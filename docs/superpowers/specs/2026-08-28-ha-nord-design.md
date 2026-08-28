# Home Assistant on Nord — Design Spec

**Date:** 2026-08-28  
**Status:** Draft (awaiting review)  
**Scope:** Выкладка Nord Ops на prod и семейная витрина Home Assistant: Container на elion, HTTPS-поддомен, custom component через REST-грань Ops (свет, климат, чайник).  
**Depends on:** [2026-08-27-nord-ops-design.md](./2026-08-27-nord-ops-design.md) (каталог Ops, REST `POST .../ops/{name}`, ключ на дом).  
**Related:** `specs/001-server-mqtt-ingestor/quickstart.md`, `specs/001-server-mqtt-ingestor/contracts/api-v1.md`

---

## 1. Problem

Nord Ops в `main`: один каталог, MCP для Telegram, REST для остальных. На elion этого образа ещё нет (миграция `008` на prod не накатана). Семейного облачного GUI нет: Grafana — наблюдатель SQL, Mosaic — LAN, Telegram — агент.

Home Assistant должен стать витриной для семьи, не мозгом дома. Мозг остаётся LogicMachine. Все внешние клиенты (Telegram, HA, кто угодно дальше) ходят в Nord одним каталогом Ops. HA не получает KNX, не получает MQTT `cm/#`, не дублирует автоматизации.

---

## 2. Vocabulary

| Термин | Значение |
|--------|----------|
| **Nord** | Один FastAPI-процесс на elion. Клиенты ходят только сюда. |
| **Ops** | Каталог операций. HA вызывает REST-грань тех же handlers, что Telegram — MCP-грань. |
| **HA Container** | Официальный образ Home Assistant без Supervisor и аддонов. Не HA OS. |
| **Витрина** | UI для людей. Состояние и команды — только Ops. Сцены дома не здесь. |
| **Сервисный ключ HA** | API-ключ Nord `name=home-assistant`, scopes `read,write`, один дом (`house`). Семья его не видит. |
| **Пользователь HA** | Логин на `ha.black-castle.ru`. Один человек — один аккаунт. В Nord не проецируется. |

Говорим: «HA на REST-грани Nord». Не говорим «HA управляет KNX» и не «HA-сервер MCP».

---

## 3. Goals

| Goal | Decision |
|------|----------|
| Сначала живой Nord Ops | Образ с `main` + alembic `008` + skill OpenClaw до любого контейнера HA |
| Единый контур | Данные и команды HA только через `GET /api/v1/ops` и `POST /api/v1/houses/{house_id}/ops/{name}` |
| Витрина, не мозг | Нет автоматизаций дома в HA; нет KNX; нет MQTT `cm/#` и `ha/#` |
| Семья на HTTPS | `https://ha.black-castle.ru`, отдельный логин HA на человека |
| Свет / климат / чайник | Сущности из `list_lights` / `get_climate` / `get_kettle`; клик → `set_lights` / `set_climate` / `set_kettle` |
| Актор | Команды с ключа HA пишут `commands.actor_key_id` отдельно от Telegram |
| Без GA в UI | `unique_id` = дом + имя зоны. Групповой адрес семья не видит |

---

## 4. Non-goals (этой спеки)

- Grafana как iframe/виджет в Lovelace (следующая волна, если понадобится).
- Энергия, `discover` как дерево устройств, живые события вместо poll.
- MQTT Discovery (`ha/#` или `cm/#`), интеграция KNX, HA OS, Supervisor, аддоны.
- Таблица `users` / OAuth в Nord; несколько домов на ключ HA.
- Перенос сцен и heating rules из LogicMachine.
- Публичная витрина на `monitoring-dev` (`AUTH_REQUIRED=false`).
- Правки TOOLS.md (issue #4) и апгрейд MCP SDK 2.x (issue #5).
- Кастомный Lovelace «на все комнаты» сверх карточек сущностей, которые HA рисует сам.

---

## 5. Approaches considered

| Подход | Суть | Решение |
|--------|------|---------|
| YAML REST sensors/кнопки | Быстро, дублирует Ops в YAML | Нет: хрупко, расходится с Telegram |
| Гибрид: сущности из `GET /objects`, команды через Ops | Больше карточек | Нет: GA утекает в HA, два контракта |
| MQTT Discovery `ha/#` | Живые апдейты | Нет в этой волне: второй протокол и ACL |
| **Custom component + poll Ops (выбран)** | Один клиент REST-грани | Да: тот же каталог, что MCP |

Сеть HA ↔ Nord:

| Подход | Суть | Решение |
|--------|------|---------|
| Bridge + `host.docker.internal:8321` | Nord слушает `-p 127.0.0.1:8321`, с bridge это часто недоступно | Нет как основной путь |
| Общая user-defined сеть к контейнеру `cottage-monitoring` | Меняет networking Nord | Не в этой волне |
| **`--network host` + HA `server_host: 127.0.0.1` (выбран)** | HA → `http://127.0.0.1:8321/api/v1`; снаружи только nginx | Да |

---

## 6. Architecture

```text
Семья (логин HA, по человеку)
        │ HTTPS
        ▼
  ha.black-castle.ru  nginx  TLS + WebSocket
        │ 127.0.0.1:8123
        ▼
  HA Container (--network host)
        │ REST + API-ключ home-assistant
        ▼
  Nord  127.0.0.1:8321/api/v1
        │ Ops dispatch
        ▼
  MQTT cm/<house>/...  →  LogicMachine

Telegram → Nord /mcp (тот же dispatch, другой ключ)
Grafana  → PostgreSQL SELECT only
```

Порядок выкладки **внутри этой спеки** (не параллельно):

1. Nord Ops на prod (образ, `008`, restart, skill, probe 16 tools).
2. Ключ `home-assistant`, smoke dry-run `POST .../ops/list_lights`.
3. HA Container + nginx + DNS + TLS.
4. Custom component + пользователи HA.

HA не стартуем, пока шаг 1–2 не зелёные.

---

## 7. Выкладка Nord Ops (шаг 1)

Как в `specs/001-server-mqtt-ingestor/quickstart.md`: код на elion не клонировать и не rsync. Сборка образа локально (`linux/amd64`), `docker save` → `docker load`. Тег systemd сейчас `cottage-monitoring:0.2.9` — новый тег после сборки `main` с Ops.

1. `alembic upgrade head` на prod-БД **до** рестарта (колонка `commands.actor_key_id`). Иначе insert команды падает.
2. Обновить unit/тег образа, `systemctl restart cottage-monitoring`.
3. Skill: `openclaw skills install … --agent cottage --force` (или копия в `workspace/skills/cottage-monitoring/`; cottage workspace — симлинк). Канон `AGENTS.md`. `openclaw mcp probe cottage` — 16 tools, есть `list_houses`. Старый чат Telegram: `/new`.
4. Проверка ключом write: `GET /api/v1/ops` — 16 имён; `POST /api/v1/houses/house/ops/list_lights` с `X-Cottage-Dry-Run` — 2xx.

Dev (`monitoring-dev`) в этой волне не делаем семейной витриной.

---

## 8. HA Container и nginx

- Образ: официальный `ghcr.io/home-assistant/home-assistant:stable` (pull на elion допустим: это не наш код).
- systemd по образцу `cottage-monitoring.service`: имя контейнера `home-assistant`, `--network host`, volume `/var/lib/homeassistant:/config`.
- В `configuration.yaml`: `http.server_host: 127.0.0.1`, `http.server_port: 8123`, `http.use_x_forwarded_for: true`, `http.trusted_proxies: [127.0.0.1]`.
- DNS: A `ha.black-castle.ru` → elion. TLS тот же контур, что у `monitoring.black-castle.ru` (certbot).
- nginx: отдельный `server` на `ha.black-castle.ru`, `proxy_pass http://127.0.0.1:8123`, **WebSocket** (`Upgrade`, `Connection`, `proxy_read_timeout` не короткий). `/mcp` Nord не открывать на этом сервере.
- Конфиг HA на volume. Custom component из репозитория: `ha/custom_components/cottage_monitoring/`. На elion не `git clone` продукта. Артефакт компонента (tar/директория) кладётся в `/var/lib/homeassistant/custom_components/cottage_monitoring/` скриптом выкладки из этой спеки.
- Интеграции KNX, MQTT, Mosquitto в этот инстанс не добавляем. `automations.yaml` пустой; семейные сценарии дома не заводим.

---

## 9. Custom component

Пакет `cottage_monitoring` (HACS-совместимый `manifest.json`, ставится нами, не из магазина в этой волне).

Конфиг интеграции (UI или YAML):

- `base_url`: `http://127.0.0.1:8321/api/v1`
- `api_key`: сервисный ключ
- `house_id`: `house`
- `scan_interval`: 30 с

Ключ в запросе: заголовок `X-API-Key` или `Authorization: Bearer` (как ресурсный REST Nord). Не MCP.

Маппинг (имена Ops неотличимы от Telegram):

| Платформа HA | Read Op | Write Op | Примечание |
|--------------|---------|----------|------------|
| `light` | `list_lights` | `set_lights` | `query` = имя зоны из `items[].name`; `skip_unchanged=true` |
| `climate` | `get_climate` | `set_climate` | зона = `zones[].room`; уставка `setpoint_c`; **`force_relay` в UI нет** |
| `switch` | `get_kettle` | `set_kettle` | один чайник |

`unique_id`: `{house_id}:{kind}:{stable_name}`. Поле `ga` из ответа Ops в атрибуты сущности не кладём (или только в debug-лог компонента, не в карточку).

Poll: координатор HA раз в `scan_interval` зовёт три read-Op. Команда — сразу `POST .../ops/{name}`. UI может показать оптимистичное состояние; истина — следующий poll. `get_command_status` в этой волне не вызываем.

Ключ HA свой: лимит `mcp_write_rate_limit_per_minute` (30) не делит корзину с Telegram.

`X-Cottage-Dry-Run` — только тесты компонента, не семейный UI.

Не регистрируем в этой волне: `get_energy_status`, `discover`, `set_commands`, `set_light` (одиночный query), `get_heating_diagnostics`.

---

## 10. Auth

Два контура.

**Семья → HA.** Отдельный пользователь Home Assistant на человека (встроенные users HA). История HA показывает, кто кликнул. В Nord все эти клики — один `actor_key_id` ключа `home-assistant`. Таблицы людей в Nord нет. nginx не ставит Basic Auth поверх HA.

**HA → Nord.** `cottage-create-api-key --house house --name home-assistant --scopes read,write`. Секрет в конфиге/secrets контейнера, не в git, не в браузере.

Первый пользователь HA (владелец инстанса) создаётся при onboarding; остальные — в UI HA Settings → People. Владелец может ставить интеграции; обычные члены семьи — нет (роль без админа).

---

## 11. Ошибки

| Ответ Nord | Поведение HA |
|------------|----------------|
| 401 / 403 | интеграция `unavailable`; не делать вид, что свет выключился |
| 429 | retry с backoff; карточка не подтверждает смену, пока write не 2xx |
| `ambiguous` / `not_found` | сущность из этого query не создаём; строка в лог HA |
| сеть / 5xx | `unavailable` до следующего poll |

---

## 12. Testing

Без живого MQTT, где возможно:

1. Fake Nord: `GET /ops` отдаёт каталог; `list_lights` → N `light` entities с именами из `items`.
2. `turn_on` зоны бьёт `POST /houses/house/ops/set_lights` с `query` = имя зоны, `on: true` (не в `set_light`, не в `set_commands`).
3. `set_temperature` зоны → `set_climate` без `force_relay` в теле.
4. Чайник → `set_kettle`.
5. Имена write/read Ops ⊆ вывод `cottage-ops catalog` (не второй хардкод списка).
6. 401 → интеграция unavailable.
7. На elion после шага 1: dry-run `list_lights`; после шага 4: poll HA видит те же имена зон.

---

## 13. Success criteria

1. На prod работает образ с Ops: probe 16 tools, `008` накатана.
2. Семья с личным логином на `https://ha.black-castle.ru` включает свет и ставит уставку климата.
3. Та же зона гасится из Telegram тем же handler `set_lights`.
4. Grafana по-прежнему только SELECT.
5. В HA нет интеграции KNX/MQTT на `cm/#` и нет домашних автоматизаций.

---

## 14. Implementation order (для плана)

1. Выкладка Nord Ops на elion (образ, 008, skill).
2. Ключ `home-assistant` + контрактные тесты компонента против fake Nord.
3. Код интеграции `ha/custom_components/cottage_monitoring/` (TDD).
4. systemd + nginx + DNS/TLS + volume.
5. Onboarding HA, пользователи семьи, smoke на доме `house`.
6. Запись operational notes в `quickstart.md` (R-xxx).

---

## 15. Risks

| Risk | Mitigation |
|------|------------|
| Рестарт Nord до alembic 008 | Чеклист: migrate, потом restart |
| Host network открывает 8123 на все интерфейсы | `http.server_host: 127.0.0.1`; проверка `ss` что 8123 только loopback |
| Poll 30 с vs выключатель на стене | То же, что у Telegram: истина в `current_state` после MQTT; карточка догонит poll |
| Член семьи ставит автоматизацию в HA | Роль без админа; пустой `automations.yaml`; в skill/доке — запрет |
| Write rate-limit при «выключить весь этаж» | Один `set_lights` на зону, не N `set_light`; свой ключ HA |

---

## 16. Follow-up (не эта спека)

- Grafana-виджет в Lovelace.
- Энергия и прочие Ops как сущности.
- Push/события вместо poll (только если 30 с мало).
- MQTT `ha/#` — только если REST-компонент не выдержит.
- Users в Nord, чтобы `actor_key_id` различал людей, а не только «HA vs Telegram».
