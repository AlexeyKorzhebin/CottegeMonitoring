# MCP Agent Bridge Implementation Plan

> **Status (2026-07-16): DONE for MVP.** Tasks 1–8 and 10 completed in production on elion (OpenClaw + localhost MCP). Task 9 (public nginx `/mcp`) **cancelled by design** — API binds `127.0.0.1` only; same-host agents only. Follow-ups landed: pymorphy3 case matching, MCP unit tests, `cottage-create-api-key` console script.

**Goal:** Add scoped API-key auth, a semantic object resolver, Streamable HTTP MCP tools (light/climate/temp/sensors), an agent skill, and nginx `/mcp` so Hermes/OpenClaw/Cursor can control the cottage safely.

**Architecture:** Approach A — MCP mounted inside the existing FastAPI app; tools call shared `object_resolver` + `state_service` / `command_service`. Same auth middleware protects `/mcp` and `/api/v1`. Spec: `docs/superpowers/specs/2026-07-15-mcp-agent-bridge-design.md`. Inventory: `docs/superpowers/specs/2026-07-15-house-objects-inventory.md`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic, Redis, official `mcp` Python SDK (or FastMCP if mount is cleaner), pytest/httpx, nginx.

---

## File map (create / modify)

| Path | Role |
|------|------|
| `server/src/cottage_monitoring/models/api_key.py` | ORM for `api_keys` |
| `server/alembic/versions/004_api_keys.py` | Migration |
| `server/src/cottage_monitoring/config.py` | `auth_required`, `mcp_command_rate_limit` |
| `server/src/cottage_monitoring/auth/keys.py` | Hash/verify, create key |
| `server/src/cottage_monitoring/auth/middleware.py` | ASGI/HTTP middleware or Depends |
| `server/src/cottage_monitoring/cli/create_api_key.py` | CLI (`cottage-create-api-key`) |
| `server/src/cottage_monitoring/services/object_resolver.py` | tag/name → objects (+ pymorphy3) |
| `server/src/cottage_monitoring/mcp/server.py` | MCP app + tools |
| `server/src/cottage_monitoring/main.py` | Mount `/mcp`, wire auth |
| `server/pyproject.toml` | `mcp`, `pymorphy3` deps |
| `server/deploy/nginx/cottage-monitoring.conf` | ~~`location /mcp`~~ **cancelled** (localhost-only) |
| `server/tests/unit/test_object_resolver.py` | Resolver + cases |
| `server/tests/unit/test_api_key_auth.py` | Auth unit tests |
| `server/tests/unit/test_mcp_tools.py` | MCP tools + auth gates |
| `skills/cottage-monitoring/SKILL.md` | Agent skill |
| `skills/cottage-monitoring/hermes.mcp.example.yaml` | Hermes snippet |

---

### Task 1: API key model + migration — DONE

### Task 2: Hash helpers + settings — DONE

### Task 3: Auth middleware on `/api/v1` + `/mcp` — DONE

### Task 4: create API key CLI — DONE (`cottage-create-api-key`)

### Task 5: object_resolver — DONE (+ Russian morphology)

### Task 6: agent_actions — DONE (incl. energy, kettle, heating diag)

### Task 7: Streamable HTTP MCP — DONE (`/mcp`, bind `127.0.0.1`)

### Task 8: Agent skill — DONE (OpenClaw on elion; Hermes example in repo)

### Task 9: nginx `/mcp` — CANCELLED

Public proxy not used. MCP is loopback-only for OpenClaw on the same host. Do not expose `/mcp` via nginx without a later security review.

### Task 10: E2E checklist — DONE

- [x] migrate + keys on prod/dev
- [x] discover / temperature / lights via MCP
- [x] set_light + kettle write smoke
- [x] set_climate kitchen smoke (raise setpoint, confirm relay / restore)
- [x] OpenClaw voice/chat prompts (user-verified)
- [x] Hermes: optional; example config only (user handles if needed)

---

## Out of scope (do not implement in this plan)

- Intent REST `/lights` `/climate`
- OAuth / multi-house keys
- Push notifications
- Changing LM tag taxonomy (document only)
- Public nginx MCP endpoint
