# Home Assistant on Nord — Design Spec

**Date:** 2026-08-28  
**Status:** Implemented  
**Scope:** Выкладка Nord Ops на prod; поля `area`/`floor`; `set_auto_heating`; чайник как `water_heater` (текущая T + вкл/выкл; слайдер уставки отложен); семейная витрина HA.  
**Depends on:** [2026-08-27-nord-ops-design.md](./2026-08-27-nord-ops-design.md) (каталог Ops, REST `POST .../ops/{name}`, ключ на дом).  
**Related:** `specs/001-server-mqtt-ingestor/quickstart.md`, `specs/001-server-mqtt-ingestor/contracts/api-v1.md`

---

## 1. Problem

Nord Ops в `main`: один каталог, MCP для Telegram, REST для остальных. На prod elion работает `cottage-monitoring:0.3.3`; alembic `008` накатана. Семейный GUI: `https://ha.black-castle.ru` (TLS, onboarding владельца пройден). Grafana — наблюдатель SQL, Mosaic — LAN, Telegram — агент. Чайник в HA: вкл/выкл и текущая T. Слайдер уставки не рисуем, пока на LogicMachine нет writable `ble_teapot_RK-M173S_setpoint` (отложено оператором). Аккаунты семьи в HA People — отдельно, не в этом изменении.

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
| **Area** | Комната в HA Area Registry (гостиная, кухня, …). Источник — поле `area` в ответах read-Ops, не таблица в компоненте. |
| **Floor** | Этаж в HA Floor Registry (`1 этаж`, `2 этаж`, `Улица`). Источник — поле `floor`: `1` \| `2` \| `outside`. |
| **Дом (area)** | Служебная area HA без этажа: онлайн дома, автоуправление полами. Не комната. |

Говорим: «HA на REST-грани Nord». Не говорим «HA управляет KNX» и не «HA-сервер MCP».

---

## 3. Goals

| Goal | Decision |
|------|----------|
| Сначала живой Nord Ops | Образ с `main` + alembic `008` + skill OpenClaw до любого контейнера HA |
| Единый контур | Данные и команды HA только через `GET /api/v1/ops` и `POST /api/v1/houses/{house_id}/ops/{name}` |
| Витрина, не мозг | Нет автоматизаций дома в HA; нет KNX; нет MQTT `cm/#` и `ha/#` |
| Семья на HTTPS | `https://ha.black-castle.ru`, отдельный логин HA на человека |
| Свет / климат / чайник | Свет: `list_lights`. Климат: ТП + датчики. Чайник: `water_heater` — вкл/выкл, **текущая T**, **уставка** через расширенный `set_kettle` |
| Датчики в комнате | Воздух, влажность, температура пола — сущности; **реле зоны только статус** (не выключатель) |
| Дом | `get_house_status` → «дом онлайн»; `get_climate.auto_heating_enabled` + новый Op `set_auto_heating` → переключатель авто ТП (GA `1/7/1`) |
| Комнаты и этажи | HA Areas + Floors из полей `area`/`floor` в read-Ops. Семья видит дом по этажам и комнатам, не плоский список |
| Актор | Команды с ключа HA пишут `commands.actor_key_id` отдельно от Telegram |
| Без GA в UI | `unique_id` = дом + kind + стабильное имя. Групповой адрес семья не видит |

---

## 4. Non-goals (этой спеки)

- Grafana как iframe/виджет в Lovelace (следующая волна, если понадобится).
- MQTT Discovery (`ha/#` или `cm/#`), интеграция KNX, HA OS, Supervisor, аддоны.
- Таблица `users` / OAuth в Nord; несколько домов на ключ HA.
- Перенос сцен и heating rules из LogicMachine.
- Публичная витрина на `monitoring-dev` (`AUTH_REQUIRED=false`).
- Правки TOOLS.md (issue #4) и апгрейд MCP SDK 2.x (issue #5).
- Ручная вёрстка Lovelace YAML «этаж = картинка». Группировка — штатные **Areas / Floors** HA.
- Энергия, `discover` как дерево устройств, живые события вместо poll.

---

## 5. Approaches considered

| Подход | Суть | Решение |
|--------|------|---------|
| YAML REST sensors/кнопки | Быстро, дублирует Ops в YAML | Нет: хрупко, расходится с Telegram |
| Гибрид: сущности из `GET /objects`, команды через Ops | Больше карточек | Нет: GA утекает в HA, два контракта |
| MQTT Discovery `ha/#` | Живые апдейты | Нет в этой волне: второй протокол и ACL |
| **Custom component + poll Ops (выбран)** | Один клиент REST-грани | Да: тот же каталог, что MCP |
| Таблица комнат в YAML компонента | HA знает «кухня = …» | Нет: комнаты живут в тегах/именах Nord |
| **`area`/`floor` в read-Ops (выбран)** | Резолвер уже матчит «кухня» / `1floor` | HA только рисует Areas/Floors |

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

1. Nord Ops на prod (образ с `set_auto_heating` и `area`/`floor`, `008`, restart, skill, probe **17** tools).
2. Поля `area`/`floor` в read-Ops (можно тем же образом, что шаг 1, если ещё не выложено).
3. Ключ `home-assistant`, smoke `list_lights` + `get_climate`.
4. HA Container + nginx + DNS + TLS.
5. Custom component (Areas/Floors, датчики) + пользователи HA.

HA не стартуем, пока шаги 1–3 не зелёные.

---

## 7. Выкладка Nord Ops (шаг 1)

Как в `specs/001-server-mqtt-ingestor/quickstart.md`: код на elion не клонировать и не rsync. Сборка образа локально (`linux/amd64`), `docker save` → `docker load`. Тег systemd: **`cottage-monitoring:0.3.0`**.

1. `alembic upgrade head` на prod-БД **до** рестарта (колонка `commands.actor_key_id`). Иначе insert команды падает.
2. Обновить unit/тег образа, `systemctl restart cottage-monitoring`.
3. Skill: `openclaw skills install … --agent cottage --force` (или копия в `workspace/skills/cottage-monitoring/`; cottage workspace — симлинк). Канон `AGENTS.md` с `set_auto_heating`.
4. `openclaw mcp probe cottage` — **17** tools (`list_houses`, `set_auto_heating`). Старый чат Telegram: `/new`.
5. Проверка ключом write: `GET /api/v1/ops` — 17 имён; dry-run `list_lights` и `get_climate` — 2xx.

Dev (`monitoring-dev`) в этой волне не делаем семейной витриной.

---

## 8. HA Container и nginx

- Образ: официальный `ghcr.io/home-assistant/home-assistant:stable` (pull на elion допустим: это не наш код).
- systemd по образцу `cottage-monitoring.service`: имя контейнера `home-assistant`, `--network host`, volume `/var/lib/homeassistant:/config`.
- HTTP-сервер: Settings → System → Network (HA 2026.8+ импортировал YAML и игнорирует блок `http:`). Канон: listen `127.0.0.1:8123`, Trust X-Forwarded-For, trusted proxy `127.0.0.1`. Не возвращать `http:` в `configuration.yaml`.
- DNS: A `ha.black-castle.ru` → elion. TLS тот же контур, что у `monitoring.black-castle.ru` (certbot).
- nginx: отдельный `server` на `ha.black-castle.ru`, `proxy_pass http://127.0.0.1:8123`, **WebSocket** (`Upgrade`, `Connection`, `proxy_read_timeout` не короткий). `/mcp` Nord не открывать на этом сервере.
- Конфиг HA на volume. Custom component из репозитория: `ha/custom_components/cottage_monitoring/`. На elion не `git clone` продукта. Артефакт компонента (tar/директория) кладётся в `/var/lib/homeassistant/custom_components/cottage_monitoring/` скриптом выкладки из этой спеки.
- Интеграции KNX, MQTT, Mosquitto в этот инстанс не добавляем. `automations.yaml` пустой; семейные сценарии дома не заводим.

---

## 9. Placement: комнаты и этажи

HA сам умеет **Floors** и **Areas**. Компонент не рисует свой план дома и не хранит список комнат. На каждом poll:

1. Берёт уникальные пары `(floor, area)` из ответов Ops.
2. Создаёт/обновляет Floor Registry: `1 этаж`, `2 этаж`, `Улица` (`outside`).
3. Создаёт/обновляет Area Registry: одно area на комнату, привязка к этажу.
4. Пишет `area_id` сущностям (свет, climate, датчики, чайник).
5. Сущности дома (онлайн, авто ТП) кладёт в area **«Дом»**, которую компонент создаёт сам — это не комната из Ops.

Семья открывает стандартный обзор по комнатам/этажам (Overview / Areas). Картинки этажей и ручной Lovelace — не эта спека.

Чтобы это не парсить из английских имён Zigbee в компоненте, **Nord добавляет поля в уже существующие read-Ops** (лишние ключи JSON; MCP/Telegram не ломаются):

| Поле | Значение |
|------|----------|
| `floor` | `1` \| `2` \| `outside` \| отсутствует. Из тегов `1floor`/`floor1`, `2floor`/`floor2`, `outside`. |
| `area` | Каноническая комната по-русски, как в KNX-именах: `кухня`, `гостиная`, `Настина комната`, … Синонимы резолвера (`зал`→гостиная, `Настя`→Настина). Zigbee `zb_sensor_fl1_living_room_*` мапится **в Nord**, не в HA. |

Где поля появляются:

- `list_lights.items[]`
- `get_climate.zones[]` (рядом с уже существующими `room`, `setpoint`, `floor_temp`, `room_temp`, `relay_on`; `area` = тот же смысл, что `room`, плюс явный `floor`)
- `get_temperature.items[]`
- `get_sensors.items[]` (для `kind=humidity` и воздуха)
- `get_kettle`: `area` кухня, если резолвер так классифицирует; иначе area не ставим

Новых имён Ops нет. Ресурсный `GET /objects` для раскладки комнат HA не используем.

---

## 10. Custom component

Пакет `cottage_monitoring` (HACS-совместимый `manifest.json`, ставится нами, не из магазина в этой волне).

Конфиг интеграции (UI или YAML):

- `base_url`: `http://127.0.0.1:8321/api/v1`
- `api_key`: сервисный ключ
- `house_id`: `house`
- `scan_interval`: 30 с

Ключ в запросе: заголовок `X-API-Key` или `Authorization: Bearer` (как ресурсный REST Nord). Не MCP.

Poll раз в `scan_interval`: `get_house_status`, `list_lights`, `get_climate`, `get_temperature`, `get_sensors` (`kind=humidity`), `get_kettle`. Команда — сразу `POST .../ops/{name}`. Оптимистичный UI; истина — следующий poll. `get_command_status` в этой волне не вызываем.

Маппинг:

| HA | Read Op | Write Op | Что видит семья |
|----|---------|----------|-----------------|
| `binary_sensor` дом онлайн | `get_house_status.online_status` | нет | Area «Дом». `on` только если статус ровно `online`; иначе off (`offline`/`unknown`/`partial`) |
| `switch` автоуправление полами | `get_climate.auto_heating_enabled` | **`set_auto_heating`** `{on: bool}` | Area «Дом». Выкл = Lua гасит все реле ТП. Не путать с реле комнаты |
| `light` в area | `list_lights` | `set_lights` (`query` = имя зоны, `skip_unchanged=true`) | Свет комнаты |
| `climate` в area | `get_climate` | `set_climate` без `force_relay` | Уставка ТП; воздух = `room_temp`; влажность карточки = датчик той же `area` |
| `binary_sensor` нагрев зоны | `get_climate.zones[].relay_on` | **нет** | Только статус реле `1/5/*`. Не `switch`, не `force_relay` |
| `sensor` температура пола | `zones[].floor_temp` / `get_temperature` `source=floor` | нет | Плёнка `1/3/*`, не воздух |
| `sensor` температура воздуха | `get_temperature` `source=air` | нет | Для графиков; climate уже показывает current |
| `sensor` влажность | `get_sensors` `kind=humidity` | нет | Zigbee `%`; улица — area «Улица» |
| `sensor` улица | `get_temperature` `source=outdoor` | нет | Area «Улица» |
| `water_heater` чайник | `get_kettle` | `set_kettle` | Кухня. Текущая T = `appliance.temp`. Уставка = `appliance.setpoint_c`. On/off = `appliance.on` (state `33/1/38`, не cmd). Отдельный `switch` не дублируем |

Климат — **тёплый пол**, не HVAC: `hvac_mode` heat, без cool/fan. Реле комнаты **не** выключатель.

Новые/расширенные Ops:

| name | permission | house_scoped | Что меняем |
|------|------------|--------------|------------|
| `set_auto_heating` | write | да | **новый** `agent_actions.set_auto_heating` → GA `1/7/1` |
| `set_kettle` | write | да | **расширить** params: `on: bool \| None`, `setpoint_c: float \| None` (хотя бы одно). `on=false` — выкл. `on=true` без уставки — кипятить (как сейчас, cmd bool). `setpoint_c` 40–100 — нагрев/поддержание, без GA в теле HA |
| `get_kettle` | read | да | JSON уже содержит `appliance.temp`. Добавить `setpoint_c`, если есть объект уставки |

Каталог: 17 имён (`set_auto_heating`; `set_kettle` не новое имя). MCP schema `set_kettle` меняется — drift/skill: «нагрей чайник до 80» → `set_kettle(setpoint_c=80)`.

**Дыра на LM (отложено 2026-08-28).** `get_kettle.appliance.setpoint_c` = `null`. Объекта уставки нет. HA показывает вкл/выкл и текущую температуру; слайдер уставки не рисуем, пока на LogicMachine нет writable setpoint (имя `ble_teapot_RK-M173S_setpoint`). Завести объект на LM — отдельная задача оператора. Не писать уставку в cmd bool.

Read авто уже есть в `get_climate` (`auto_heating_enabled`). Отдельный `get_auto_heating` не заводим. В `SKILL.md` / каноне AGENTS: «авто полы» → `set_auto_heating`; чайник до N °C → `set_kettle(setpoint_c)`. Telegram по-прежнему спрашивает перед выключением авто ТП. HA — явный switch/слайдер.

`get_house_status.last_seen` можно атрибутом binary_sensor, не отдельной карточкой.

`unique_id`: `{house_id}:{kind}:{stable_name}`. `ga` в карточку не кладём.

Ключ HA свой: лимит write/мин не делит корзину с Telegram.

`X-Cottage-Dry-Run` — только тесты компонента.

Не регистрируем: `get_energy_status`, `discover`, `set_commands`, `set_light`, `get_heating_diagnostics`, батареи Zigbee (follow-up).

---

## 11. Auth

Два контура.

**Семья → HA.** Отдельный пользователь Home Assistant на человека (встроенные users HA). История HA показывает, кто кликнул. В Nord все эти клики — один `actor_key_id` ключа `home-assistant`. Таблицы людей в Nord нет. nginx не ставит Basic Auth поверх HA.

**HA → Nord.** `cottage-create-api-key --house house --name home-assistant --scopes read,write`. Секрет в конфиге/secrets контейнера, не в git, не в браузере.

Первый пользователь HA (владелец инстанса) создаётся при onboarding; остальные — в UI HA Settings → People. Владелец может ставить интеграции; обычные члены семьи — нет (роль без админа).

---

## 12. Ошибки

| Ответ Nord | Поведение HA |
|------------|----------------|
| 401 / 403 | интеграция `unavailable`; не делать вид, что свет выключился |
| 429 | retry с backoff; карточка не подтверждает смену, пока write не 2xx |
| `ambiguous` / `not_found` | сущность из этого query не создаём; строка в лог HA |
| сеть / 5xx | `unavailable` до следующего poll |

---

## 13. Testing

Без живого MQTT, где возможно:

1. Fake Nord: `list_lights` → lights; у items есть `area`/`floor`; в HA появились соответствующие Area и Floor.
2. `turn_on` зоны → `POST .../ops/set_lights` с `query` = имя зоны, `on: true`.
3. `set_temperature` зоны → `set_climate` без `force_relay`.
4. Climate зоны: `current_temperature` = `room_temp`, `current_humidity` с датчика той же `area`; рядом sensor пола = `floor_temp`.
5. `get_sensors kind=humidity` → sensor влажности в той же area, не «плоский» список без комнаты.
6. Чайник: `water_heater` current = `temp`; `set_operation` on/off → `set_kettle(on=…)`; `set_temperature` → `set_kettle(setpoint_c=…)` (не отдельный switch).
7. Реле зоны — `binary_sensor`, вызов `set_climate` с `force_relay` из HA отсутствует.
8. Switch авто ТП → `POST .../ops/set_auto_heating` `{on: true/false}`; read с `get_climate.auto_heating_enabled`.
9. `get_house_status` → binary_sensor онлайн; `partial`/`unknown` = off.
10. Имена Ops ⊆ `cottage-ops catalog` (17 имён).
11. 401 → unavailable.
12. На elion: dry-run `list_lights` / `get_climate`; poll HA — комнаты плюс area «Дом».

---

## 14. Success criteria

1. На prod работает образ с Ops: probe **17** tools, `008` накатана, есть `set_auto_heating`.
2. Семья на `https://ha.black-castle.ru` видит **этажи и комнаты**; в комнате — свет, уставка ТП, воздух, влажность, температура пола, **статус реле (не рубильник)**; на кухне — чайник с текущей T и вкл/выкл (слайдер уставки отложен до объекта LM); в «Дом» — онлайн и автоуправление полами (на Обзоре в избранном).
3. Та же зона гасится из Telegram тем же handler `set_lights`.
4. Grafana по-прежнему только SELECT.
5. В HA нет интеграции KNX/MQTT на `cm/#` и нет домашних автоматизаций.

---

## 15. Implementation order (для плана)

1. Выкладка Nord Ops на elion (образ, 008, skill).
2. Поля `area`/`floor` в read-Ops; Op `set_auto_heating`; расширить `get_kettle`/`set_kettle` (уставка). Live: если на LM нет setpoint-объекта чайника — завести его, иначе слайдер не включать.
3. Ключ `home-assistant` + контрактные тесты компонента против fake Nord (включая Areas и датчики).
4. Код интеграции `ha/custom_components/cottage_monitoring/` (TDD).
5. systemd + nginx + DNS/TLS + volume.
6. Onboarding HA, пользователи семьи, smoke: комната (климат + датчики + статус реле); area «Дом» (онлайн + авто ТП).
7. Operational notes в `quickstart.md` (R-xxx).

---

## 16. Risks

| Risk | Mitigation |
|------|------------|
| Рестарт Nord до alembic 008 | Чеклист: migrate, потом restart |
| Host network открывает 8123 на все интерфейсы | `http.server_host: 127.0.0.1`; проверка `ss` что 8123 только loopback |
| Poll 30 с vs выключатель на стене | То же, что у Telegram: истина в `current_state` после MQTT; карточка догонит poll |
| Член семьи ставит автоматизацию в HA | Роль без админа; пустой `automations.yaml`; в skill/доке — запрет |
| Write rate-limit при «выключить весь этаж» | Один `set_lights` на зону, не N `set_light`; свой ключ HA |
| Zigbee имена на английском | Маппинг `area` только в Nord, одним словарём с резолвером |
| Случайно выключить авто ТП | Явное имя «Автоуправление полами»; выкл гасит реле скриптом LM. Реле комнат — не switch |
| Реле зоны принять за рубильник | Только `binary_sensor`; `force_relay` из HA запрещён |
| Слайдер чайника без GA уставки | Сначала объект на LM; HA не пишет °C в cmd bool |
| Гостиная 1 / гостиная 2 (две уставки ТП) | Два climate в одном area «гостиная», имена зон различаются; не два area |

---

## 17. Follow-up (не эта спека)

- Grafana-виджет в Lovelace.
- Энергия как сущности HA.
- Батареи Zigbee как sensor в той же area.
- Ручной Lovelace / картинки этажей.
- Push/события вместо poll (только если 30 с мало).
- MQTT `ha/#` — только если REST-компонент не выдержит.
- Users в Nord, чтобы `actor_key_id` различал людей, а не только «HA vs Telegram».
