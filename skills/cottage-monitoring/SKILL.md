---
name: cottage-monitoring
description: Control and monitor the cottage via CottageMonitoring MCP (lights, climate, sensors, energy). Use when the user asks about home temperature, heating, lights, electricity, or smart devices.
---

# Cottage Monitoring MCP

Connect agents (Hermes, OpenClaw, Cursor) to the CottageMonitoring MCP server.

## Connection (localhost only)

MCP/API bind to **loopback only** (`127.0.0.1`) on the elion host — no public nginx URL by design.

- **MCP URL (prod, same host):** `http://127.0.0.1:8321/mcp`
- **MCP URL (dev, same host):** `http://127.0.0.1:8322/mcp`
- **Auth:** `Authorization: Bearer cm_<secret>` (API key scoped to one house)

### OpenClaw / mcporter (elion)

1. Prefer tools via mcporter alias `cottage` → prod `http://127.0.0.1:8321/mcp`.
2. Optional alias `cottage-dev` → `http://127.0.0.1:8322/mcp`.
3. `mcporter list cottage --schema` then `mcporter call cottage.<tool> ...`.
4. See `references/openclaw-connection.md` on the OpenClaw host.

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
| «Как дела у дома?» / online | `get_house_status` |
| «Найди объект…» | `discover` |
| «Температура в …» (комната) | `get_temperature` — **air** from Zigbee `33/1/*` |
| «Температура пола» | `get_temperature` — source `floor` (`1/3/*`) |
| «Влажность» | `get_sensors` kind=sensor |
| «Свет в …» read | `list_lights` / `discover` kind=light |
| «Включи/выключи свет» | `set_light` |
| «Отопление / тёплые полы» read | `get_climate` + `get_heating_diagnostics` |
| «Поставь 22 градуса» (ТП) | `set_climate` — **setpoint only** |
| «Сколько жрём электричества» | `get_energy_status` |
| «Статус чайника» | `get_kettle` (summary: on/state/temp) |
| «Включи чайник» | `set_kettle` (пишет в `33/1/39` cmd) |
| После команды | `get_command_status` |

## Heating rules (critical)

From `manage_warm_floor.lua`:

1. **`1/7/1`** — auto balancing algorithm ON/OFF. Do **not** toggle without explicit user request.
2. **`set_climate`** writes **setpoint** (`1/6/*`) only. It does **not** turn on floor relays — algorithm manages `1/4/*`.
3. **`force_relay`** on `set_climate` is **debug-only** — warn the user.
4. Room comfort temp → Zigbee air sensors (`33/1/*`, tag `temperature`).
5. Floor sensor temp → `1/3/*` (inside the film, not room air).
6. Diagnostics ready-to-read → `get_heating_diagnostics` (`34/1/*`).

## Safety

- If `discover` or `set_*` returns `ambiguous`, ask the user which room/device.
- Read before write when unsure.
- Do not spam commands; one action per user request.
- API key = full house access within scopes (`read` / `write`).
- Prefer loopback MCP; do not expose `/mcp` publicly.

## Synonyms

- зал / гостиная
- Настя / Настина комната
- Тим / Тимина / Тимнина комната
- уличное / улица / outdoor / двор / снаружи → tag `outside` (крыльцо, терраса, балкон)
