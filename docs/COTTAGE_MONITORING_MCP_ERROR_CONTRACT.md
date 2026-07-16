# CottageMonitoring MCP error contract

**Source of truth:** `AlexeyKorzhebin/CottegeMonitoring` (this repo)  
**Image pin:** `server/deploy/IMAGE_PIN.yaml`

## Tool result shapes

### Success

Tools return JSON text with domain payload, e.g. `{"request_id": "...", "ga": "...", "status": "sent"}`.

### Ambiguous resolver (`set_light`, `set_climate`, …)

```json
{
  "status": "ambiguous",
  "candidates": [{"name": "...", "ga": "..."}]
}
```

No MQTT command is sent. No `request_id`.

### Domain error (404, 429, …)

```json
{
  "status": "error",
  "code": 404,
  "error": "No light found for: ..."
}
```

Implemented in `cottage_monitoring/mcp/server.py` via `_with_session` (maps `HTTPException`).

### Scope error

```json
{
  "status": "error",
  "code": 403,
  "error": "Scope 'write' required"
}
```

## Resolver rule (v0.2.0+)

Multiple matches → `ambiguous` **even when** caller passes explicit `role` (e.g. two `LIGHT_CONTROL` for «гостиная торшер»).

Exception: `kind=light` without `role` — auto-pick single control if exactly one control among matches.

## Consumer guidance (OpenClaw / Hermes)

- On `ambiguous`: ask user which candidate; do not retry write blindly.
- On `error`: show `error` field to user; do not treat as success.
- Overlay images (`structured-errors-*`) are **retired** — use versioned image from this repo.
