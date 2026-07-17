# Grafana dashboards — Cottage Monitoring

Provisioned dashboards for house telemetry from PostgreSQL/TimescaleDB
(`cottage_monitoring.events` + `current_state` + `objects`).

## Dashboards (folder **Cottage**)

| UID | Title | Contents |
|-----|-------|----------|
| `cottage-overview` | Overview | Instant: online, auto-heat, Total P, daily kWh, outdoor °C; lights & floor relays tables; room air temps |
| `cottage-energy` | Electricity | Power/Q/S/PF/Hz; Total P & per-phase P; Urms/Irms; hourly kWh |
| `cottage-climate` | Climate | Air temp & humidity timeseries; weather now; floor vs setpoint; relay history |
| `cottage-lights` | Lights | Instant ON/OFF table + 0/1 history by floor |
| `cottage-batteries` | Batteries | Zigbee battery % table |
| `cottage-lm-load` | LM Load | loadavg 1/5/15 мин (GA `34/1/6..8`); суточная статистика |

URLs (behind nginx):

- https://elion.black-castle.ru/grafana/d/cottage-overview/
- https://elion.black-castle.ru/grafana/d/cottage-energy/
- https://elion.black-castle.ru/grafana/d/cottage-climate/
- https://elion.black-castle.ru/grafana/d/cottage-lights/
- https://elion.black-castle.ru/grafana/d/cottage-batteries/
- https://elion.black-castle.ru/grafana/d/cottage-lm-load/

## Selected metrics (from house inventory)

Kept the curated / high-signal set; dropped raw meter internals and unused stubs.

- **Energy:** `32/1/35` Total P, per-phase P/U/I, PF, Hz, hour/daily/total kWh
- **Air:** Zigbee `33/1/*` temperature & humidity (main rooms) + outdoor `32/5/*`
- **Heat:** floor temps `1/3/*`, setpoints `1/6/*`, relay status `1/5/*`, auto `1/7/1`
- **Lights:** status GAs `1/2/*` (instant + history)

- **LM / monitoring:** loadavg `34/1/6` (1м), `34/1/7` (5м), `34/1/8` (15м) — дашборд `cottage-lm-load`, алерт load15 > 2.0

## Cursor / MCP access (elion)

Grafana on elion is **OSS** — Grafana Assistant CLI (Cloud A2A) **не работает**.
Для вопросов по графикам из Cursor используем **mcp-grafana**:

1. Service account `cursor-mcp` (Editor), token: `/etc/cottage-monitoring/grafana-mcp.token` (на elion)
2. Локально токен: `~/.config/grafana-mcp/token`
3. Cursor MCP (`~/.cursor/mcp.json`) → server `grafana` → `https://elion.black-castle.ru/grafana`

После правки mcp.json: **Cursor → Reload Window** / перезапуск MCP.

## Deploy


```bash
./server/deploy/grafana/deploy.sh
```

Creates read-only role `cottage_grafana`, datasource UID `cottage-monitoring-pg`,
and file-provisions JSON under `/var/lib/grafana/dashboards/cottage`.

DB password: `/etc/cottage-monitoring/grafana-db.password` (server only, not in git).

### Alerts (Telegram)

Secrets file on elion (preferred):

```bash
# /etc/cottage-monitoring/telegram.env  (root:root 600)
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

Example: `server/deploy/telegram.env.example`. Fallback: OpenClaw gateway process env.

```bash
./server/deploy/grafana/deploy_alerts.sh
```

Creates contact point `cottage-telegram`, route `team=cottage`, alerts:
- **Cottage house offline or stale**
- **Cottage LM load15 high** (`34/1/8` > 2.0 for 10m → Telegram warning)

## Notes

- `current_state.ga` may use dash form (`1-2-3`); SQL normalizes with `replace(ga,'-','/')`.
- Timeseries use `$__timeGroupAlias` over `events` (hypertable) to downsample.
- Grafana 12 stores provisioned dashboards in unified storage (may not show in classic `dashboard` sqlite table).
