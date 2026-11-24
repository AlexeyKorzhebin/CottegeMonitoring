#!/usr/bin/env bash
# Set LM root password via temporary resident + os.execute (old FW has no webrequest;
# Apps .lp is NOT root — passwd/chpasswd from .lp fails).
#
# Usage:
#   LM_SSH_PASSWORD='...' ./deploy/lm-set-root-pass.sh
#   # or password already in secrets/lm.env
#
# After failed SSH attempts LM ipblocker may DROP your LAN IP on :22 —
# this script also clears INPUT DROP for your current en0/en1 address.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SECRETS_FILE="${LM_SECRETS_FILE:-$PROJECT_ROOT/secrets/lm.env}"

if [[ -f "$SECRETS_FILE" ]]; then
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
RESIDENT_ID="${LM_PASS_RESIDENT_ID:-67}"
PASS="${LM_SSH_PASSWORD:-}"

if [[ -z "$FTP_PASS" || -z "$ADMIN_PASS" ]]; then
  echo "Need LM_FTP_PASSWORD and LM_ADMIN_PASSWORD in $SECRETS_FILE" >&2
  exit 1
fi
if [[ -z "$PASS" ]]; then
  echo "Set LM_SSH_PASSWORD in env or $SECRETS_FILE" >&2
  exit 1
fi
if [[ ! "$PASS" =~ ^[A-Za-z0-9]+$ ]]; then
  echo "LM_SSH_PASSWORD must be alphanumeric (safe for shell/passwd pipe)" >&2
  exit 1
fi

LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

cat >"$TMPDIR/cm_set_root_pass.lua" <<EOF
-- one-shot: root password via os.execute (resident = uid 0)
local pass = '$PASS'
local marker = '/tmp/cm_root_pass.done'
os.remove(marker)
local cmd = string.format(
  "printf '%%s\\n%%s\\n' '%s' '%s' | passwd root >%s 2>&1; echo RC:\$? >>%s; id >>%s 2>&1",
  pass, pass, marker, marker, marker
)
os.execute(cmd)
EOF

UNBAN_LUA=""
if [[ -n "$LAN_IP" ]]; then
  UNBAN_LUA=$(cat <<EOF
os.execute('iptables -D INPUT -p tcp -s $LAN_IP --dport 22 -j DROP 2>/dev/null || true')
EOF
)
fi

cat >"$TMPDIR/cm_set_root_pass_run.lp" <<EOF
<?
require('apps')
local json = require('json')
local SRC = '/home/apps/store/data/cottage-monitoring/cm_set_root_pass.lua'
local ID = $RESIDENT_ID
local f = io.open(SRC, 'r')
if not f then
  print(json.encode({ ok = false, err = 'src missing' }))
  return
end
local code = f:read('*a')
f:close()
db:update('scripting', { script = code, active = 1, type = 'resident' }, { id = ID })
os.remove('/tmp/cm_root_pass.done')
os.execute(string.format(
  'rm -f /var/run/gs-resident-%d.pid; (lua /lib/genohm-scada/core/scripting-resident.lua %d >/tmp/cm_root_pass_spawn.log 2>&1 </dev/null &)',
  ID, ID))
os.execute('sleep 2')
$UNBAN_LUA
local mf = io.open('/tmp/cm_root_pass.done', 'r')
local marker = mf and mf:read('*a') or nil
if mf then mf:close() end
db:update('scripting', {
  script = '-- create_shell_pass stub (inactive)\\n',
  active = 0,
}, { id = ID })
os.execute('rm -f /var/run/gs-resident-' .. ID .. '.pid')
os.remove(SRC)
if setheader then setheader('Content-Type', 'application/json; charset=utf-8') end
print(json.encode({
  ok = marker ~= nil and marker:find('changed', 1, true) ~= nil,
  marker = marker,
  unban_ip = '$LAN_IP',
}))
?>
EOF

echo "Upload + run resident id=$RESIDENT_ID on $HOST (unban=$LAN_IP)..."
lftp -u "$FTP_USER","$FTP_PASS" "ftp://$HOST" -e "
set xfer:clobber yes
cd data/cottage-monitoring
put $TMPDIR/cm_set_root_pass.lua -o cm_set_root_pass.lua
put $TMPDIR/cm_set_root_pass_run.lp -o cm_set_root_pass_run.lp
bye
"

curl -sS -u "$ADMIN_USER:$ADMIN_PASS" -H "Referer: http://$HOST/apps/" \
  --max-time 40 "http://$HOST/apps/data/cottage-monitoring/cm_set_root_pass_run.lp"
echo

lftp -u "$FTP_USER","$FTP_PASS" "ftp://$HOST" -e "
set xfer:clobber yes
cd data/cottage-monitoring
rm -f cm_set_root_pass_run.lp cm_set_root_pass.lua
bye
" >/dev/null 2>&1 || true

echo "Done. Test: ssh -o PreferredAuthentications=password root@$HOST"
echo "Password is LM_SSH_PASSWORD from secrets (not printed)."
