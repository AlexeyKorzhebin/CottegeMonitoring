#!/usr/bin/env bash
# HTTP stop/start/restart LM Apps daemon (credentials из secrets/lm.env).
# Usage: ./deploy/lm-apps.sh stop|start|restart|pause-wd|hold-wd|health

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SECRETS_FILE="${LM_SECRETS_FILE:-$PROJECT_ROOT/secrets/lm.env}"

if [ -f "$SECRETS_FILE" ]; then
  set -a
  # shellcheck source=/dev/null
  source "$SECRETS_FILE"
  set +a
fi

HOST="${LM_HOST:-192.168.100.130}"
USER="${LM_ADMIN_USER:-admin}"
PASS="${LM_ADMIN_PASSWORD:-}"
ACTION="${1:-}"

if [ -z "$PASS" ] || [ -z "$ACTION" ]; then
  echo "Usage: $0 stop|start|restart|pause-wd|hold-wd|health"
  echo "Нужен secrets/lm.env с LM_ADMIN_PASSWORD (см. secrets/lm.env.example)."
  exit 1
fi

auth=(-u "$USER:$PASS" -H "Referer: http://$HOST/apps/")

case "$ACTION" in
  stop)    curl -sS "${auth[@]}" "http://$HOST/apps/request.lp?action=stop&name=cottage-monitoring"; echo ;;
  start)   curl -sS "${auth[@]}" "http://$HOST/apps/request.lp?action=start&name=cottage-monitoring"; echo ;;
  restart) curl -sS "${auth[@]}" "http://$HOST/apps/request.lp?action=restart&name=cottage-monitoring"; echo ;;
  pause-wd) curl -sS "${auth[@]}" "http://$HOST/apps/data/cottage-monitoring/wd_pause.lp"; echo ;;
  hold-wd)  curl -sS "${auth[@]}" "http://$HOST/apps/data/cottage-monitoring/wd_hold.lp"; echo ;;
  health)   curl -sS "${auth[@]}" "http://$HOST/apps/data/cottage-monitoring/health_get.lp"; echo ;;
  *)
    echo "Unknown action: $ACTION"
    exit 1
    ;;
esac
