# OpenClaw connection (elion)

## Native MCP (preferred, agent `cottage`)

OpenClaw-managed server in `~/.openclaw/openclaw.json`:

```json
"mcp": {
  "servers": {
    "cottage": {
      "url": "http://127.0.0.1:8321/mcp",
      "transport": "streamable-http",
      "headers": { "Authorization": "Bearer ${COTTAGE_API_KEY}" },
      "connectTimeout": 10,
      "timeout": 30,
      "supportsParallelToolCalls": true,
      "toolFilter": { "exclude": ["resources_*", "prompts_*"] }
    }
  }
}
```

Agent tool policy:

- `cottage`: `profile: "minimal"`, `alsoAllow: ["bundle-mcp"]` (no `exec`)
- `main`: `deny: ["bundle-mcp"]`

Ops:

```bash
# as openclaw, with user systemd dbus
openclaw mcp probe cottage          # expect 17 house tools, including list_houses and set_auto_heating
openclaw mcp doctor cottage
openclaw mcp reload                 # after config change
# gateway already has COTTAGE_API_KEY via EnvironmentFile cottage-env
```

Smoke (no Telegram deliver; single-house key — omit `house_id`):

```bash
openclaw agent --agent cottage \
  --session-key agent:cottage:smoke \
  --message "Верни online_status и active_object_count" \
  --json --timeout 120
# expect toolCall cottage__get_house_status without house_id, not exec/mcporter
```

Operator catalog check (not for the `cottage` agent — `exec` stays forbidden):

```bash
cottage-ops catalog
cottage-ops catalog --json
# same names as the Ops registry / MCP tools/list
```

Live `TOOLS.md` агента `cottage` (`workspace-cottage/TOOLS.md`) — native MCP only. Канон: `specs/001-server-mqtt-ingestor/openclaw-cottage-tools.md`. mcporter в этом файле не путь агента. `mcporter generate-cli` / CLI-снимок — тоже не путь агента (R-026).

## Legacy mcporter (benches / shell debug)

- mcporter alias: `cottage` → prod `http://127.0.0.1:8321/mcp`
- Optional alias: `cottage-dev` → `http://127.0.0.1:8322/mcp`
- Dry-run: `cottage-dry` + header `X-Cottage-Dry-Run: 1`
- Auth: `COTTAGE_API_KEY` / secrets under `~/.openclaw/secrets/cottage-prod-api-key`
- List tools: `mcporter list cottage --schema` (not `list-commands`)
- Call: `mcporter call cottage.get_house_status`

### MCP session reuse (keep-alive)

Each ephemeral `mcporter call` opens a new MCP HTTP session (`Created new transport with session ID`).
For multi-step agent turns that adds handshake overhead. Enable keep-alive:

`~/.openclaw/workspace/config/mcporter.json`:

```json
"cottage": {
  "baseUrl": "http://127.0.0.1:8321/mcp",
  "headers": { "Authorization": "Bearer ${COTTAGE_API_KEY}" },
  "lifecycle": "keep-alive"
}
```

```bash
cd ~/.openclaw/workspace
mcporter --config ./config/mcporter.json daemon start
mcporter daemon status   # cottage: idle
```

Verify: two consecutive calls should log only **one** `Created new transport` on the server.

Create key (on host, after image deploy):

```bash
sudo docker run --rm --network=host \
  --env-file /etc/cottage-monitoring/cottage-monitoring.prod.env \
  --entrypoint cottage-create-api-key cottage-monitoring:latest \
  --house <house_id> --name openclaw --scopes read,write
```

MCP binds loopback only — not exposed via public nginx.
