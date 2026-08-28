---
name: cottage-monitoring
description: Control and monitor the cottage via CottageMonitoring MCP (lights, climate, sensors, energy). Use when the user asks about home temperature, heating, lights, electricity, or smart devices.
---

# Cottage Monitoring MCP

Connect agents (Hermes, OpenClaw, Cursor) to the CottageMonitoring MCP face of Nord.

## Connection (localhost only)

MCP binds to **loopback only** (`127.0.0.1`) on the elion host — no public nginx URL by design. OpenClaw uses this MCP face, not a separate MCP server. Do not call Grafana or Mosaic.

- **MCP URL (prod, same host):** `http://127.0.0.1:8321/mcp`
- **MCP URL (dev, same host):** `http://127.0.0.1:8322/mcp`
- **Auth:** `Authorization: Bearer cm_<secret>` (API key with grants on one or more houses)

### OpenClaw (elion) — native MCP

1. **Preferred:** OpenClaw `mcp.servers.cottage` → prod `http://127.0.0.1:8321/mcp` (tools appear as `cottage__<tool>`).
2. Agent `cottage`: `tools.profile=minimal` + `alsoAllow: ["bundle-mcp"]` (no `exec` — do not invent CLI).
3. Agent `main`: `tools.deny: ["bundle-mcp"]` so house tools stay out of the general chat.
4. Auth: `Authorization: Bearer ${COTTAGE_API_KEY}` (gateway env from `~/.openclaw/secrets/cottage-env`).
5. Optional/legacy: mcporter alias `cottage` / `cottage-dev` for benches and shell debugging — see `references/openclaw-connection.md`.

### Hermes example (`~/.hermes/config.yaml`)

```yaml
mcp_servers:
  cottage:
    url: http://127.0.0.1:8321/mcp
    headers:
      Authorization: "Bearer ${COTTAGE_API_KEY}"
```

Store `COTTAGE_API_KEY` in env — never commit it.

## Tool selection

| User intent | Tool |
|-------------|------|
| «Какой дом / список домов» | `list_houses` |
| «Как дела у дома?» / online | `get_house_status` |
| «Найди объект…» | `discover` |
| «Температура в …» (комната) | `get_temperature` — **air** from Zigbee `33/1/*` |
| «Температура пола» | `get_temperature` — source `floor` (`1/3/*`) |
| «Влажность» | `get_sensors` kind=sensor |
| «Свет в …» read | `list_lights` / `discover` kind=light |
| «Включи/выключи свет» (одна лампа/комната) | `set_light` |
| «Выключи свет на 1 этаже» / зона / улица | `set_lights` — **один batch**, не цикл `set_light`. Skip смотрит status (`1/2/*`), не control |
| «Отопление / тёплые полы» read | `get_climate` + `get_heating_diagnostics` |
| «Поставь 22 градуса» (ТП) | `set_climate` — **setpoint only** |
| «Авто полы / автоуправление отоплением» | `set_auto_heating` (`on`) — **спроси** перед выкл |
| «Сколько жрём электричества» | `get_energy_status` |
| «Статус чайника» / teapot | `get_kettle` |
| «Включи/выключи чайник» | `set_kettle` |
| «Нагрей чайник до 80» | `set_kettle(setpoint_c=80)` — не cmd bool |
| Нестандартное устройство по имени | см. **Routing ladder** ниже |
| После команды | `get_command_status` |

## Routing ladder (critical)

Порядок выбора tool — сверху вниз. Вызывай native MCP tools (`cottage__…` / имена ниже). **Не** используй `exec` / `mcporter list` / `list-commands`. На «детальнее / подробнее» сразу `get_temperature` + `get_energy_status` (+ `get_climate` при отоплении). Схемы аргументов — в MCP `tools/list`, не дублируй их.

1. **Дом** — `list_houses` перед house-scoped tools, если домов может быть больше одного:
   - `house_id` на house-scoped tools **опционален**.
   - `list_houses` вернул один дом (или ключ однодомный) — **не** передавать `house_id` (как сейчас).
   - вернул больше одного — каждый последующий tool **с** `house_id`. Не выбирать первый дом молча. Если пользователь не назвал дом — спросить.
   - чужой / неизвестный дом — не выдумывать; опереться на 403.
2. **Семантический tool**, если интент ясен:
   - зона/этаж/улица света → `set_lights`
   - одна лампа / торшер / подсветка по имени → `set_light`
   - чайник / teapot / Redmond → `set_kettle` / `get_kettle` (**не** `set_lights`, **не** поиск среди ламп)
   - чайник до N °C → `set_kettle` с `setpoint_c`
   - авто полы / автоуправление отоплением → `set_auto_heating`
   - уставка ТП → `set_climate`
   - отчёт / энергия / климат read → соответствующие `get_*`
3. **Имя устройства без зоны** (торшер, подсветка стола, розетка «X») → сразу `set_light` / `discover` с этим query.
4. **Неизвестный прибор** (не свет/климат/чайник) → `discover(query="<имя>", kind="all")` или `kind="appliance"`.
   - Нашёл control GA → действуй через подходящий tool (`set_light` если light_control; иначе `set_commands` с `[{ga,value}]` если это единственный однозначный control).
   - `ambiguous` → спроси пользователя, покажи 2–5 кандидатов.
   - Пусто → скажи, что не нашёл; не выдумывай GA.
5. Не ограничивайся только светом/климатом/отчётом — чайник и прочие appliance входят в MCP.

## Heating rules (critical)

From `manage_warm_floor.lua`:

1. **`1/7/1`** — auto balancing algorithm ON/OFF. Toggle only via `set_auto_heating` after explicit confirm; do not write `1/7/1` through `set_commands` unless user named the GA.
2. **`set_climate`** writes **setpoint** (`1/6/*`) only. It does **not** turn on floor relays — algorithm manages `1/4/*`.
3. **`force_relay`** on `set_climate` is **debug-only** — warn the user.
4. Room comfort temp → Zigbee air sensors (`33/1/*`, tag `temperature`).
5. Floor sensor temp → `1/3/*` (inside the film, not room air).
6. Diagnostics ready-to-read → `get_heating_diagnostics` (`34/1/*`).

## Safety

- If `discover` or `set_*` returns `ambiguous`, ask the user which room/device.
- Read before write when unsure.
- Do not spam commands; one action per user request.
- **Performance:** never loop `set_light` for a floor/zone — use `set_lights` once. One `get_command_status` per `request_id`, not per lamp. `cmd_timeout` is 60s — N sequential commands can take minutes.
- API key = machine grants on house(s) within scopes (`read` / `write`). Not a user login.
- Prefer loopback MCP; do not expose `/mcp` publicly.

## Synonyms

- зал / гостиная
- Настя / Настина комната
- Тим / Тимина / Тимнина комната
- уличное / улица / outdoor / двор / снаружи → tag `outside` (крыльцо, терраса, балкон)
- чайник / чайник Redmond / teapot → `set_kettle` / `get_kettle`

Query matching lemmatizes Russian cases (`кухне`/`кухню` → кухня, `крыльце` → крыльцо). Prefer natural language queries.

## Ops: create API key

On elion (image has console script)::

```bash
sudo docker run --rm --network=host \
  --env-file /etc/cottage-monitoring/cottage-monitoring.prod.env \
  --entrypoint cottage-create-api-key cottage-monitoring:latest \
  --house <house_id> --name openclaw --scopes read,write
```

Prints `api_key=cm_…` once — store under `~/.openclaw/secrets/`.
