# MCP Agent Bridge — Design Spec

**Date:** 2026-07-15  
**Status:** Approved (approach A)  
**Scope:** Analysis & design only — implementation tracked in `docs/superpowers/plans/2026-07-15-mcp-agent-bridge.md`  
**Related inventory:** [2026-07-15-house-objects-inventory.md](./2026-07-15-house-objects-inventory.md)

## 1. Problem

CottegeMonitoring already has a cloud FastAPI + MQTT path to LogicMachine/KNX, but agents (Hermes, OpenClaw, Cursor, etc.) cannot safely use it:

- No MCP server exists (only mentioned as future goal in constitution / specs).
- REST `/api/v1` has **no authentication** (network/nginx only).
- API is GA-centric; voice assistants need semantic ops (light/climate/temp), not group addresses.

## 2. Goals

| Goal | Decision |
|------|----------|
| Clients | Universal MCP (Hermes, OpenClaw, Cursor, …) |
| Primary UX | Home voice/chat assistant |
| Tool level | Semantic (`set_light`, `get_temperature`, …) |
| Auth | API key bound to `house_id`, scopes `read` / `write` |
| Deployment | Streamable HTTP MCP **inside** the same FastAPI process on elion |
| Architecture | **Approach A**: semantic MCP tools + shared object resolver; keep existing REST |

## 3. Non-goals (MVP)

- Separate intent REST (`/lights`, `/climate`) — defer until UI needs it.
- OAuth 2.1 / multi-user accounts.
- Auto-understanding unnamed/untagged GAs.
- Push alerts to agents (v2: poll/events).
- Standalone MCP sidecar process (approach C).

## 4. Architecture

```text
Hermes / OpenClaw / Cursor
        |  Authorization: Bearer cm_<key>
        v
┌───────────────────────────────────────────┐
│ FastAPI (same Docker / uvicorn)           │
│  /mcp          Streamable HTTP MCP        │
│  /api/v1       existing REST              │
│  Auth middleware (API key → house, scopes)│
│  object_resolver (tag + name → GA)        │
│  state_service / command_service          │
└───────────────────┬───────────────────────┘
                    │ MQTT …/v1/cmd
                    v
              LogicMachine → KNX
```

**Why A:** fastest path to useful agent tools; resolver + services can later power intent REST (B) without rewriting tools. Sidecar (C) doubles deploy cost with no win for one process on elion.

**Transport:** Streamable HTTP MCP at `/mcp` (exact subpath per SDK). Hermes configs already support `url` + `headers`.

**Library (implementation choice):** official Python MCP SDK or FastMCP mounted on the ASGI app — pick the one that mounts cleanly on current FastAPI ≥0.115 / uvicorn.

## 5. Authentication

### 5.1 Data model `api_keys`

| Column | Notes |
|--------|--------|
| `id` | UUID PK |
| `name` | Human label (`hermes-home`) |
| `key_prefix` | First 8 chars for lookup/logs |
| `key_hash` | SHA-256 (or similar) of secret; **never** store plaintext |
| `house_id` | FK → houses; one house per key (MVP) |
| `scopes` | text[] / JSON: `read`, `write` |
| `created_at`, `revoked_at`, `last_used_at` | |

Client sends `Authorization: Bearer cm_…` or `X-API-Key: cm_…`.

### 5.2 Enforcement

- Same middleware for `/mcp` and `/api/v1` (except `/health`; `/metrics` stays IP-restricted via nginx).
- Without `write`, mutate tools return a clear agent-readable error.
- Migration flag `AUTH_REQUIRED` (default `true` in prod after keys exist; allow `false` briefly in local/tests).
- Key generation CLI: `python -m cottage_monitoring.scripts.create_api_key --house … --scopes read,write` → prints plaintext **once**.

### 5.3 Scopes

| Scope | Tools |
|-------|--------|
| `read` | `get_house_status`, `discover`, `get_temperature`, `get_sensors`, `list_lights` / `get_light`, `get_climate`, `get_command_status` |
| `write` | all of `read` + `set_light`, `set_climate` |

## 6. Object resolver

Inputs: `house_id` (from key), `query` (room / Russian name fragment), optional `kind`.

Kind → tag filters (from real house inventory):

| kind | Prefer tags / rules |
|------|---------------------|
| `light` | `light` + `control` for write; `light` + `status` for feedback |
| `temp` | Floor sensors: `temp`+`heat` without `setpoint`; air: `temperature` / `zb_sensor`; outdoor: `weather`+`temp` |
| `climate` | Read: setpoint `setpoint`+`heat`; on/off `control`+`heat`; status `status`+`heat` |
| `sensor` | `temp`, `humidity`, `meter`, `weather`, `occupancy`, … |
| `all` | no kind filter |

Matching: case-insensitive substring on `name` and tag tokens (`1floor`, `гостиная`, …). Only `is_active=true`.

**Disambiguation rule:** 0 matches → not found; 1 → use it; >1 → return candidates, **never** silently pick.

**Light write target:** control GA (`tag` has `control` + `light`), not `:status`.  
**Climate setpoint write:** GA with `setpoint` (+ `heat`). Optional on/off via `control`+`heat`. Prefer not writing to floor raw (`32/3/*`) or master `1/6/1` unless explicitly requested.

## 7. MCP tool surface (MVP)

| Tool | Scope | Behavior |
|------|-------|----------|
| `get_house_status` | read | online, last_seen, counts |
| `discover` | read | `query`, optional `kind` → list of {name, ga, tags, kind} |
| `get_temperature` | read | room query or all meaningful temps (floor + zb/air + outdoor) |
| `get_sensors` | read | filter by kind/tag/query + current state |
| `list_lights` / `get_light` | read | lights + prefer status value when present |
| `set_light` | write | resolve control light → `send_command(bool)`; return `request_id` / ack |
| `get_climate` | read | for room: temp + setpoint + relay status if resolvable |
| `set_climate` | write | primarily **setpoint** (°C); optional `heating_on` bool to control ТП relay |
| `get_command_status` | read | poll by `request_id` |

### 7.1 Climate specifics (from inventory)

Real house has clear GA families:

- Setpoints: `1/6/2`…`1/6/15` — tags `heat,setpoint,temp`, names `Уставка ТП - <room>`
- Relay control: `1/4/*` — `control,heat`, names `ТП - <room>`
- Relay status: `1/5/*` — `heat,status`
- Floor temp: `1/3/*` — `heat,temp` (not setpoint)
- Auto master: `1/7/1` `Автоматическое управление отоплением` (`auto,heat`)
- Master setpoint `1/6/1` has **empty tags** — exclude from default discover unless query contains `master`

`set_climate(room, setpoint=22)` → resolver finds unique `setpoint` object for room → command float/int as today MQTT allows.

## 8. Safety

- Active objects only.
- Rate limit writes (e.g. N commands/min per key) — Redis counter.
- Audit log: `key_id`, tool, ga, value, outcome.
- Skill instructs agent: read before write; ask user on ambiguous discover; no command spam.
- Optional later: confirm for “all lights off”.

## 9. Agent skill

Deliverable path: `skills/cottage-monitoring/SKILL.md` (+ short Hermes/OpenClaw config snippets).

Contents:

- MCP URL (`https://monitoring.black-castle.ru/mcp` / dev counterpart)
- How to set `Authorization: Bearer …`
- Tool routing examples (“температура в зале” → `get_temperature`; “свет на кухне” → `discover`/`set_light`)
- Ambiguity and safety rules
- Secret handling note

## 10. Dependencies / risks

| Risk | Mitigation |
|------|------------|
| Room synonyms (зал ≈ гостиная) | skill aliases + discover; optional synonym map later |
| Dual temp sources (floor `1/3` vs Zigbee `33/1`) | `get_temperature` returns both with labels; prefer zb `temperature` tag when query is “воздух” |
| Opening REST to internet with auth | require auth on `/api/v1`; keep metrics locked |
| Auth break local tests | pytest fixture issues test key; or `AUTH_REQUIRED=false` in test env |

## 11. Success criteria (design)

1. Agents get semantic tools + skill, not raw GA API.
2. Auth model is scoped API key → single house.
3. MCP lives in FastAPI over HTTP.
4. Built on existing `state_service` / `command_service` + object tags.
5. MVP exclusions are explicit.

## 12. Implementation phases (summary)

1. Auth (model, middleware, CLI, alembic)
2. Object resolver + unit tests against inventory fixtures
3. MCP tools mount + integration tests
4. Skill + Hermes/OpenClaw examples
5. nginx `/mcp`, deploy, issue prod key

Detailed steps: `docs/superpowers/plans/2026-07-15-mcp-agent-bridge.md`.
