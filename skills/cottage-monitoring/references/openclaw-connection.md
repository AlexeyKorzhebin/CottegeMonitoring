# OpenClaw connection (elion)

- mcporter alias: `cottage` → prod `http://127.0.0.1:8321/mcp`
- Optional alias: `cottage-dev` → `http://127.0.0.1:8322/mcp`
- Auth: `COTTAGE_API_KEY` / secrets under `~/.openclaw/secrets/cottage-prod-api-key`
- List tools: `mcporter list cottage --schema`
- Call: `mcporter call cottage.get_house_status`

## MCP session reuse (keep-alive)

Each ephemeral `mcporter call` opens a new MCP HTTP session (`Created new transport with session ID`).
For multi-step agent turns (ListTools → set_lights → get_command_status) that adds handshake
overhead on every tool. Enable keep-alive so the daemon holds one session open:

`~/.openclaw/workspace/config/mcporter.json`:

```json
"cottage": {
  "baseUrl": "http://127.0.0.1:8321/mcp",
  "headers": { "Authorization": "Bearer ${COTTAGE_API_KEY}" },
  "lifecycle": "keep-alive"
}
```

Start daemon (auto-restarts via `systemd --user` unit `mcporter-daemon.service`):

```bash
cd ~/.openclaw/workspace
mcporter --config ./config/mcporter.json daemon start
mcporter daemon status   # cottage: idle
```

Verify: two consecutive calls should log only **one** `Created new transport` on the server.
- Create key (on host, after image deploy):

```bash
sudo docker run --rm --network=host \
  --env-file /etc/cottage-monitoring/cottage-monitoring.prod.env \
  --entrypoint cottage-create-api-key cottage-monitoring:latest \
  --house <house_id> --name openclaw --scopes read,write
```

MCP binds loopback only — not exposed via public nginx.
