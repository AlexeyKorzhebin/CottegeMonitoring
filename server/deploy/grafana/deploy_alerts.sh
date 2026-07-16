#!/usr/bin/env bash
# Deploy Grafana Telegram contact point + cottage offline alert on elion.
# Uses OpenClaw TELEGRAM_BOT_TOKEN / TELEGRAM_OWNER_ID and Grafana MCP token.
# Email is intentionally NOT configured.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "== deploy cottage Grafana Telegram alerts to elion =="
ssh elion 'bash -s' <<'REMOTE'
set -euo pipefail

GRAFANA_URL="${GRAFANA_URL:-http://127.0.0.1:3000}"
TOKEN=$(sudo cat /etc/cottage-monitoring/grafana-mcp.token)

# Telegram credentials from OpenClaw gateway process
GW_PID=$(pgrep -f "gateway --port 18789" | head -1 || true)
if [[ -z "${GW_PID}" ]]; then
  echo "ERROR: OpenClaw gateway not running — cannot read TELEGRAM_BOT_TOKEN" >&2
  exit 1
fi
ENV_FILE="/proc/${GW_PID}/environ"
BOT_TOKEN=$(tr '\0' '\n' < "$ENV_FILE" | sed -n 's/^TELEGRAM_BOT_TOKEN=//p' | head -1)
CHAT_ID=$(tr '\0' '\n' < "$ENV_FILE" | sed -n 's/^TELEGRAM_OWNER_ID=//p' | head -1)
if [[ -z "${BOT_TOKEN}" || -z "${CHAT_ID}" ]]; then
  echo "ERROR: TELEGRAM_BOT_TOKEN / TELEGRAM_OWNER_ID missing in gateway env" >&2
  exit 1
fi
echo "Telegram chat_id=${CHAT_ID} token_prefix=${BOT_TOKEN:0:6}***"

auth=(-H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" -H "X-Disable-Provenance: true")

echo "== contact point cottage-telegram =="
# Delete previous if exists (idempotent)
EXISTING=$(curl -s "${auth[@]}" "${GRAFANA_URL}/api/v1/provisioning/contact-points" \
  | python3 -c "import sys,json; cps=json.load(sys.stdin); print(next((c.get('uid','') for c in cps if c.get('name')=='cottage-telegram'), ''))")
if [[ -n "${EXISTING}" ]]; then
  curl -s -o /dev/null -w "delete=%{http_code}\n" -X DELETE "${auth[@]}" \
    "${GRAFANA_URL}/api/v1/provisioning/contact-points/${EXISTING}" || true
fi

CP_PAYLOAD=$(python3 - <<PY
import json
print(json.dumps({
  "name": "cottage-telegram",
  "type": "telegram",
  "settings": {
    "bottoken": "${BOT_TOKEN}",
    "chatid": "${CHAT_ID}",
    "parse_mode": "HTML",
    "message": "{{ len .Alerts.Firing }} firing / {{ len .Alerts.Resolved }} resolved\\n{{ range .Alerts }}\\n• {{ .Labels.alertname }}: {{ .Annotations.summary }}\\n{{ end }}"
  }
}))
PY
)
CP_RESP=$(curl -s -w "\n%{http_code}" -X POST "${auth[@]}" \
  -d "${CP_PAYLOAD}" \
  "${GRAFANA_URL}/api/v1/provisioning/contact-points")
CP_CODE=$(echo "$CP_RESP" | tail -1)
CP_BODY=$(echo "$CP_RESP" | sed '$d')
echo "contact-point HTTP ${CP_CODE}"
if [[ "${CP_CODE}" != "202" && "${CP_CODE}" != "200" ]]; then
  echo "$CP_BODY" >&2
  exit 1
fi

echo "== notification policy (route cottage alerts to telegram) =="
POLICY=$(curl -s "${auth[@]}" "${GRAFANA_URL}/api/v1/provisioning/policies")
NEW_POLICY=$(echo "$POLICY" | python3 -c '
import sys, json
p = json.load(sys.stdin)
routes = p.get("routes") or []
routes = [r for r in routes if not (
  isinstance(r.get("object_matchers"), list)
  and any(m[:2] == ["team", "="] and m[2] == "cottage" for m in r.get("object_matchers") or [])
)]
routes.insert(0, {
  "receiver": "cottage-telegram",
  "object_matchers": [["team", "=", "cottage"]],
  "continue": False,
  "group_by": ["alertname", "house_id"],
  "group_wait": "30s",
  "group_interval": "5m",
  "repeat_interval": "4h",
})
p["routes"] = routes
if not p.get("receiver"):
  p["receiver"] = "email receiver"
print(json.dumps(p))
')
POL_CODE=$(curl -s -o /tmp/grafana-policy-resp.json -w "%{http_code}" -X PUT "${auth[@]}" \
  -d "${NEW_POLICY}" \
  "${GRAFANA_URL}/api/v1/provisioning/policies")
echo "policy HTTP ${POL_CODE}"
if [[ "${POL_CODE}" != "202" && "${POL_CODE}" != "200" ]]; then
  cat /tmp/grafana-policy-resp.json >&2
  exit 1
fi

FOLDER_UID="ffsa6lrlntse8b"
DS_UID="cottage-monitoring-pg"
RULE_UID="cottage-house-stale"

echo "== alert rule ${RULE_UID} =="
# Delete existing
curl -s -o /dev/null -X DELETE "${auth[@]}" \
  "${GRAFANA_URL}/api/v1/provisioning/alert-rules/${RULE_UID}" || true

RULE_PAYLOAD=$(python3 - <<PY
import json
rule = {
  "uid": "${RULE_UID}",
  "title": "Cottage house offline or stale",
  "ruleGroup": "cottage-reliability",
  "folderUID": "${FOLDER_UID}",
  "condition": "C",
  "noDataState": "Alerting",
  "execErrState": "Alerting",
  "for": "5m",
  "annotations": {
    "summary": "House telemetry missing >15m or online_status != online",
    "description": "Controller may be up but MQTT client stuck. Check LM daemon / watchdog."
  },
  "labels": {
    "team": "cottage",
    "severity": "critical",
    "house_id": "house"
  },
  "data": [
    {
      "refId": "A",
      "relativeTimeRange": {"from": 600, "to": 0},
      "datasourceUid": "${DS_UID}",
      "model": {
        "editorMode": "code",
        "format": "table",
        "rawQuery": True,
        "rawSql": (
          "SELECT\\n"
          "  CASE\\n"
          "    WHEN online_status IS DISTINCT FROM 'online' THEN 1\\n"
          "    WHEN last_seen IS NULL THEN 1\\n"
          "    WHEN last_seen < now() - interval '15 minutes' THEN 1\\n"
          "    ELSE 0\\n"
          "  END AS value\\n"
          "FROM houses\\n"
          "WHERE house_id = 'house' AND is_active = true"
        ),
        "refId": "A"
      }
    },
    {
      "refId": "B",
      "relativeTimeRange": {"from": 600, "to": 0},
      "datasourceUid": "__expr__",
      "model": {
        "type": "reduce",
        "expression": "A",
        "reducer": "last",
        "refId": "B",
        "settings": {"mode": "replaceNN", "replaceWithValue": 1}
      }
    },
    {
      "refId": "C",
      "relativeTimeRange": {"from": 600, "to": 0},
      "datasourceUid": "__expr__",
      "model": {
        "type": "threshold",
        "expression": "B",
        "refId": "C",
        "conditions": [{
          "evaluator": {"type": "gt", "params": [0]},
          "operator": {"type": "and"},
          "query": {"params": ["C"]},
          "reducer": {"type": "last", "params": []},
          "type": "query"
        }]
      }
    }
  ]
}
print(json.dumps(rule))
PY
)
RULE_RESP=$(curl -s -w "\n%{http_code}" -X POST "${auth[@]}" \
  -d "${RULE_PAYLOAD}" \
  "${GRAFANA_URL}/api/v1/provisioning/alert-rules")
RULE_CODE=$(echo "$RULE_RESP" | tail -1)
RULE_BODY=$(echo "$RULE_RESP" | sed '$d')
echo "alert-rule HTTP ${RULE_CODE}"
if [[ "${RULE_CODE}" != "201" && "${RULE_CODE}" != "200" && "${RULE_CODE}" != "202" ]]; then
  echo "$RULE_BODY" >&2
  exit 1
fi

echo "== telegram smoke (sendMessage) =="
SMOKE=$(curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
  -d "chat_id=${CHAT_ID}" \
  --data-urlencode "text=Cottage Monitoring: Grafana alert channel configured ($(date -u +%Y-%m-%dT%H:%MZ))" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print("ok" if d.get("ok") else d)')
echo "telegram smoke: ${SMOKE}"

echo "OK: cottage-telegram contact point + alert rule deployed"
REMOTE
