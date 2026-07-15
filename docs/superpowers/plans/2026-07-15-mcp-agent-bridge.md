# MCP Agent Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

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
| `server/src/cottage_monitoring/scripts/create_api_key.py` | CLI |
| `server/src/cottage_monitoring/services/object_resolver.py` | tag/name → objects |
| `server/src/cottage_monitoring/mcp/server.py` | MCP app + tools |
| `server/src/cottage_monitoring/mcp/tools.py` | Tool handlers |
| `server/src/cottage_monitoring/main.py` | Mount `/mcp`, wire auth |
| `server/pyproject.toml` | Add `mcp` dependency |
| `server/deploy/nginx/cottage-monitoring.conf` | `location /mcp` |
| `server/tests/unit/test_object_resolver.py` | Resolver tests |
| `server/tests/unit/test_api_key_auth.py` | Auth unit tests |
| `server/tests/integration/test_mcp_tools.py` | MCP + commands path |
| `skills/cottage-monitoring/SKILL.md` | Agent skill |
| `skills/cottage-monitoring/hermes.mcp.example.yaml` | Hermes snippet |
| `docs/objects_fixture_min.json` (optional) | Tiny fixture from inventory for unit tests |

---

### Task 1: API key model + migration

**Files:**
- Create: `server/src/cottage_monitoring/models/api_key.py`
- Modify: `server/src/cottage_monitoring/models/__init__.py` (export if present)
- Create: `server/alembic/versions/004_api_keys.py`

- [ ] **Step 1: Write failing test for model columns**

```python
# server/tests/unit/test_api_key_model.py
from cottage_monitoring.models.api_key import ApiKey

def test_api_key_tablename():
    assert ApiKey.__tablename__ == "api_keys"
```

- [ ] **Step 2: Run test — expect ImportError / missing model**

Run: `cd server && pytest tests/unit/test_api_key_model.py -v`  
Expected: FAIL (module missing)

- [ ] **Step 3: Implement model**

```python
# models/api_key.py — sketch
class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    house_id: Mapped[str] = mapped_column(String(64), ForeignKey("houses.house_id"), nullable=False)
    scopes: Mapped[list] = mapped_column(JSONB, nullable=False)  # ["read","write"]
    created_at: Mapped[datetime] = ...
    revoked_at: Mapped[datetime | None] = ...
    last_used_at: Mapped[datetime | None] = ...
```

- [ ] **Step 4: Alembic revision `004_api_keys`** creating the table + index on `key_prefix`.

- [ ] **Step 5: Run unit test + `alembic upgrade head` on devops/dev DB (via tunnel if needed)**

- [ ] **Step 6: Commit** `feat(auth): add api_keys table`

---

### Task 2: Key hashing helpers + settings

**Files:**
- Create: `server/src/cottage_monitoring/auth/__init__.py`
- Create: `server/src/cottage_monitoring/auth/keys.py`
- Modify: `server/src/cottage_monitoring/config.py`

- [ ] **Step 1: Failing tests**

```python
from cottage_monitoring.auth.keys import generate_api_key, hash_api_key, verify_api_key

def test_generate_and_verify_roundtrip():
    raw, prefix = generate_api_key()
    assert raw.startswith("cm_")
    h = hash_api_key(raw)
    assert verify_api_key(raw, h)
    assert not verify_api_key(raw + "x", h)
```

- [ ] **Step 2: Run — FAIL missing module**

- [ ] **Step 3: Implement** `generate_api_key` (secrets), `hash_api_key` (sha256 of raw), `verify_api_key` (compare_digest). Add settings:

```python
auth_required: bool = True
mcp_write_rate_limit_per_minute: int = 30
```

- [ ] **Step 4: Tests PASS**

- [ ] **Step 5: Commit** `feat(auth): api key hash helpers and settings`

---

### Task 3: Auth dependency / middleware

**Files:**
- Create: `server/src/cottage_monitoring/auth/deps.py`
- Modify: `server/src/cottage_monitoring/api/*.py` or central router dependency
- Modify: `server/tests/conftest.py` / integration fixtures for `AUTH_REQUIRED=false` or inject test key

**Behavior:**
- Extract Bearer / `X-API-Key`
- If `auth_required=False`, skip (tests/local)
- Else lookup by prefix → verify hash → reject revoked → require `house_id` match when path has `{house_id}` → attach `request.state.api_key`
- `/health` always open; `/metrics` unchanged

- [ ] **Step 1: Integration test** — with `auth_required=True`, `GET /api/v1/houses` without key → 401; with valid key → 200

- [ ] **Step 2: Run — FAIL (no auth)**

- [ ] **Step 3: Implement `get_api_key_context` FastAPI dependency; apply to `api_router`

Also: when path includes `house_id`, assert `context.house_id == house_id` → else 403.

- [ ] **Step 4: Tests PASS** (update existing integration tests to set `auth_required=False` or register fixture key)

- [ ] **Step 5: Commit** `feat(auth): require API key on /api/v1`

---

### Task 4: CLI create-api-key

**Files:**
- Create: `server/src/cottage_monitoring/scripts/create_api_key.py`
- Optional: `[project.scripts]` entry in `pyproject.toml`

- [ ] **Step 1: Implement async script** argparse `--house`, `--name`, `--scopes read,write` → insert row → print raw key once

- [ ] **Step 2: Smoke-run against local/dev DB**

- [ ] **Step 3: Commit** `feat(auth): create_api_key CLI`

---

### Task 5: Object resolver

**Files:**
- Create: `server/src/cottage_monitoring/services/object_resolver.py`
- Create: `server/tests/unit/test_object_resolver.py`
- Optional fixture rows from inventory

**API sketch:**

```python
@dataclass
class ResolvedObject:
    ga: str
    name: str
    tags: list[str]
    role: str  # control|status|setpoint|sensor|other

class ResolveResult:
    matches: list[ResolvedObject]
    status: Literal["ok","not_found","ambiguous"]

async def resolve(session, house_id, *, query: str | None, kind: str | None) -> ResolveResult: ...
```

Kind filters per design/inventory:
- `light` write → need `control`+`light`
- `light` read status → prefer `status`+`light` when asking state
- `climate` setpoint → `setpoint`
- `climate` relay → `control`+`heat`
- `temp` → (`temp`+`heat` without setpoint) OR `temperature` OR (`weather`+`temp`)
- Exclude empty-name; exclude master unless query has `master`

- [ ] **Step 1: Unit tests** with in-memory list or mocked Object rows: кухня light unique; гостиная light ambiguous; setpoint кухня; master hidden by default

- [ ] **Step 2: FAIL**

- [ ] **Step 3: Implement resolver**

- [ ] **Step 4: PASS**

- [ ] **Step 5: Commit** `feat(mcp): object_resolver for semantic tools`

---

### Task 6: Semantic service helpers (thin)

**Files:**
- Create: `server/src/cottage_monitoring/services/agent_actions.py`

Wrap: resolve → get state → send_command (reuse logic from `api/commands.py` for device_id resolution).

Functions: `set_light`, `set_climate_setpoint`, `get_temperatures`, `list_lights_with_state`, …

- [ ] **Step 1: Unit/integration tests** calling helpers against DB fixture + mocked MQTT publish if needed

- [ ] **Step 2: Implement minimal helpers**

- [ ] **Step 3: Commit** `feat(mcp): agent_actions service layer`

---

### Task 7: MCP server mount + tools

**Files:**
- Add dependency `mcp` to `server/pyproject.toml`
- Create: `server/src/cottage_monitoring/mcp/server.py`, `tools.py`
- Modify: `server/src/cottage_monitoring/main.py`
- Create: `server/tests/integration/test_mcp_tools.py`

Tools to register (names from design):

`get_house_status`, `discover`, `get_temperature`, `get_sensors`, `list_lights`, `get_light`, `set_light`, `get_climate`, `set_climate`, `get_command_status`

Auth: MCP HTTP transport must see same API key (pass through Starlette Request or middleware). Write tools check `"write" in scopes`. Rate-limit writes via Redis INCR with TTL 60s.

- [ ] **Step 1: Add dependency; research mount pattern** for Streamable HTTP on FastAPI (pin working version)

- [ ] **Step 2: Failing integration test** — POST/GET MCP initialize or tool call with key returns tool list / set_light path (mock send_command)

- [ ] **Step 3: Implement mount at `/mcp`

- [ ] **Step 4: Tests PASS**

- [ ] **Step 5: Commit** `feat(mcp): streamable HTTP MCP tools`

---

### Task 8: Agent skill + Hermes example

**Files:**
- Create: `skills/cottage-monitoring/SKILL.md`
- Create: `skills/cottage-monitoring/hermes.mcp.example.yaml`

SKILL.md must include:
- MCP URL prod/dev
- Auth header
- Tool chooser table
- Disambiguation + synonyms (зал→гостиная, Настя/Тим)
- Safety: no spam; don’t flip `auto` without confirm; write uses control/setpoint only

Hermes example:

```yaml
mcp_servers:
  cottage:
    url: https://monitoring.black-castle.ru/mcp
    headers:
      Authorization: "Bearer ${COTTAGE_API_KEY}"
```

- [ ] **Step 1: Write skill + example**

- [ ] **Step 2: Commit** `docs(mcp): agent skill and Hermes config example`

---

### Task 9: nginx + deploy notes

**Files:**
- Modify: `server/deploy/nginx/cottage-monitoring.conf` (prod + dev blocks)

```nginx
location /mcp {
    proxy_pass http://cottage_monitoring_prod;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;
    proxy_read_timeout 3600s;
}
```

- [ ] **Step 1: Patch nginx config similarly for dev upstream**

- [ ] **Step 2: Document in skill or `server/README.md`:** migrate → create key → rebuild image locally → deploy per project rules (no rsync code)

- [ ] **Step 3: Commit** `chore(deploy): proxy /mcp via nginx`

---

### Task 10: End-to-end verification checklist

- [ ] **Step 1:** `alembic upgrade head` on tunnelled DB  
- [ ] **Step 2:** Create key for real `house_id`  
- [ ] **Step 3:** Local/Docker: `discover` + `get_temperature` with key  
- [ ] **Step 4:** `set_light` on a safe outdoor/test light → confirm ack + state  
- [ ] **Step 5:** `set_climate` setpoint on one room → confirm value  
- [ ] **Step 6:** Point Hermes/OpenClaw at `/mcp` with Bearer key; run one voice-like prompt  
- [ ] **Step 7:** Final commit if fixes needed

---

## Out of scope (do not implement in this plan)

- Intent REST `/lights` `/climate`
- OAuth / multi-house keys
- Push notifications
- Changing LM tag taxonomy (document only)

## Spec self-check

- Design + inventory linked above; climate = setpoints `1/6/*` + optional relay — no invented GAs
- Auth applies to REST and MCP
- Bite-sized TDD tasks for auth → resolver → MCP → skill → deploy
