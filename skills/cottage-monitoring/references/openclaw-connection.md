# OpenClaw connection (elion)

- mcporter alias: `cottage` → prod `http://127.0.0.1:8321/mcp`
- Optional alias: `cottage-dev` → `http://127.0.0.1:8322/mcp`
- Auth: `COTTAGE_API_KEY` / secrets under `~/.openclaw/secrets/cottage-prod-api-key`
- List tools: `mcporter list cottage --schema`
- Call: `mcporter call cottage.get_house_status`
- Create key (on host, after image deploy):

```bash
sudo docker run --rm --network=host \
  --env-file /etc/cottage-monitoring/cottage-monitoring.prod.env \
  --entrypoint cottage-create-api-key cottage-monitoring:latest \
  --house <house_id> --name openclaw --scopes read,write
```

MCP binds loopback only — not exposed via public nginx.
