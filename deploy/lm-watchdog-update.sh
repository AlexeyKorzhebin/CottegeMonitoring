#!/usr/bin/env bash
# Обновить Resident watchdog на LM без Web UI (FTP + db:update + respawn).
# Usage: ./deploy/lm-watchdog-update.sh [resident_id]
# Требует: secrets/lm.env (FTP + admin HTTP); для respawn — SSH root на LM
#   (alias lm_estate в ~/.ssh/config или LM_SSH_USER/LM_SSH_PASSWORD в lm.env).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SECRETS_FILE="${LM_SECRETS_FILE:-$PROJECT_ROOT/secrets/lm.env}"
WD_SRC="$PROJECT_ROOT/cm-client/scripts/watchdog-resident.lua"
RESIDENT_ID="${1:-73}"
REMOTE_WD="cm_wd_new.lua"
REMOTE_UPD="cm_script_update.lp"

if [ -f "$SECRETS_FILE" ]; then
  set -a
  # shellcheck source=/dev/null
  source "$SECRETS_FILE"
  set +a
fi

HOST="${LM_HOST:-192.168.100.130}"
FTP_USER="${LM_FTP_USER:-apps}"
FTP_PASS="${LM_FTP_PASSWORD:-}"
ADMIN_USER="${LM_ADMIN_USER:-admin}"
ADMIN_PASS="${LM_ADMIN_PASSWORD:-}"
SSH_USER="${LM_SSH_USER:-root}"
SSH_HOST="${LM_SSH_HOST:-$HOST}"

if [ -z "$FTP_PASS" ] || [ -z "$ADMIN_PASS" ]; then
  echo "Нужен secrets/lm.env с LM_FTP_PASSWORD и LM_ADMIN_PASSWORD"
  exit 1
fi

if [ ! -f "$WD_SRC" ]; then
  echo "Не найден $WD_SRC"
  exit 1
fi

TMP_UPD="$(mktemp)"
trap 'rm -f "$TMP_UPD"' EXIT

cat > "$TMP_UPD" <<EOF
<?
require('apps')
local json = require('json')
local SRC = '/home/apps/store/data/cottage-monitoring/$REMOTE_WD'
local ID = $RESIDENT_ID
local f = io.open(SRC, 'r')
if not f then
  print(json.encode({ ok = false, msg = 'source not found' }))
  return
end
local code = f:read('*a')
f:close()
local before = db:getone("SELECT LENGTH(script) FROM scripting WHERE id=" .. ID)
pcall(function() db:update('scripting', { script = code }, { id = ID }) end)
local after = db:getone("SELECT LENGTH(script) FROM scripting WHERE id=" .. ID)
if setheader then setheader('Content-Type', 'application/json; charset=utf-8') end
print(json.encode({ ok = true, resident_id = ID, len_before = before, len_after = after, src_len = #code }))
?>
EOF

echo "Upload watchdog + update helper to LM (resident id=$RESIDENT_ID)..."
lftp -u "$FTP_USER","$FTP_PASS" "ftp://$HOST" -e "
set xfer:clobber yes
cd data/cottage-monitoring
put $WD_SRC -o $REMOTE_WD
put $TMP_UPD -o $REMOTE_UPD
bye
"

auth=(-u "$ADMIN_USER:$ADMIN_PASS" -H "Referer: http://$HOST/apps/")
echo "Update scripting table..."
curl -sS "${auth[@]}" "http://$HOST/apps/data/cottage-monitoring/$REMOTE_UPD"
echo

echo "Respawn resident process (SSH)..."
SSH_OPTS=(-o StrictHostKeyChecking=no -o ConnectTimeout=15)
REMOTE_CMD="rm -f /var/run/gs-resident-${RESIDENT_ID}.pid; (lua /lib/genohm-scada/core/scripting-resident.lua ${RESIDENT_ID} >/tmp/wd${RESIDENT_ID}.log 2>&1 </dev/null &); sleep 2; ps w | grep 'scripting-resident.lua ${RESIDENT_ID}' | grep -v grep || echo NOT_RUNNING"

if [ -n "${LM_SSH_PASSWORD:-}" ]; then
  if ! command -v expect >/dev/null 2>&1; then
    echo "LM_SSH_PASSWORD задан, но expect не найден — respawn вручную по quickstart"
    exit 1
  fi
  export LM_SSH_PASS="$LM_SSH_PASSWORD"
  expect <<EOSCRIPT
set timeout 30
set pass \$env(LM_SSH_PASS)
spawn ssh ${SSH_OPTS[*]} ${SSH_USER}@${SSH_HOST} {$REMOTE_CMD}
expect {
  -nocase -re password: { send "\$pass\r"; exp_continue }
  eof
}
EOSCRIPT
elif ssh -o BatchMode=yes "${SSH_OPTS[@]}" "${SSH_USER}@${SSH_HOST}" true 2>/dev/null; then
  ssh "${SSH_OPTS[@]}" "${SSH_USER}@${SSH_HOST}" "$REMOTE_CMD"
else
  echo "SSH недоступен (ключ или LM_SSH_PASSWORD). Обновление в БД выполнено; respawn вручную:"
  echo "  ssh ${SSH_USER}@${SSH_HOST} \"$REMOTE_CMD\""
fi

echo "Cleanup remote helper files..."
lftp -u "$FTP_USER","$FTP_PASS" "ftp://$HOST" -e "
cd data/cottage-monitoring
rm -f $REMOTE_WD $REMOTE_UPD
bye
" 2>/dev/null || true

echo "Done."
