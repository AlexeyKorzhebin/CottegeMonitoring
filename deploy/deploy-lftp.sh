#!/usr/bin/env bash
# Deploy cm-client to LogicMachine controller via lftp (FTP).
# Usage:
#   ./deploy/deploy-lftp.sh              # host/user/pass из secrets/lm.env
#   ./deploy/deploy-lftp.sh [host] [user] [password]   # явные аргументы
#
# Секреты: скопируй secrets/lm.env.example → secrets/lm.env (файл в .gitignore).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCE_DIR="$PROJECT_ROOT/cm-client"
SECRETS_FILE="${LM_SECRETS_FILE:-$PROJECT_ROOT/secrets/lm.env}"

if [ -f "$SECRETS_FILE" ]; then
  # shellcheck disable=SC1090
  set -a
  # shellcheck source=/dev/null
  source "$SECRETS_FILE"
  set +a
fi

REMOTE_APP_PATH="data/cottage-monitoring"
REMOTE_DAEMON_PATH="daemon/cottage-monitoring"

HOST="${1:-${LM_HOST:-192.168.100.130}}"
USER="${2:-${LM_FTP_USER:-apps}}"
PASS="${3:-${LM_FTP_PASSWORD:-}}"

if [ -z "$PASS" ]; then
  echo "Нет пароля FTP."
  echo "  1) cp secrets/lm.env.example secrets/lm.env  и заполни LM_FTP_PASSWORD"
  echo "  2) или: $0 <host> <user> <password>"
  exit 1
fi

cd "$SOURCE_DIR"

echo "Uploading app to $REMOTE_APP_PATH (host=$HOST user=$USER)..."
if lftp -u "$USER","$PASS" "ftp://$HOST" -e "
cd $REMOTE_APP_PATH
lcd $SOURCE_DIR
mirror -R .
bye
" 2>/dev/null; then
  echo "  -> uploaded to $REMOTE_APP_PATH"
else
  echo "  -> cd $REMOTE_APP_PATH failed, trying current directory..."
  lftp -u "$USER","$PASS" "ftp://$HOST" -e "
lcd $SOURCE_DIR
mirror -R .
bye
"
  echo "  -> uploaded to FTP root (app directory)"
fi

APP_NAME="cottage-monitoring"
echo "Uploading daemon to daemon/$APP_NAME/..."
if lftp -u "$USER","$PASS" "ftp://$HOST" -e "
cd daemon
mkdir $APP_NAME
cd $APP_NAME
lcd $SOURCE_DIR/daemon
put daemon.lua
bye
" 2>/dev/null; then
  echo "  -> daemon uploaded to daemon/$APP_NAME/daemon.lua"
else
  echo "  -> trying store/daemon path..."
  if lftp -u "$USER","$PASS" "ftp://$HOST" -e "
cd store/daemon
mkdir $APP_NAME
cd $APP_NAME
lcd $SOURCE_DIR/daemon
put daemon.lua
bye
" 2>/dev/null; then
    echo "  -> daemon uploaded to store/daemon/$APP_NAME/daemon.lua"
  else
    echo "  WARNING: daemon upload failed. Manual: cd daemon/$APP_NAME; put cm-client/daemon/daemon.lua"
  fi
fi

echo ""
echo "Verify — files in $REMOTE_APP_PATH:"
lftp -u "$USER","$PASS" "ftp://$HOST" -e "
cd $REMOTE_APP_PATH
cls -1
bye
" 2>/dev/null || lftp -u "$USER","$PASS" "ftp://$HOST" -e "cls -1" 2>/dev/null

echo ""
echo "Deployed. App URL: http://$HOST/apps/data/cottage-monitoring/"
echo "Daemon restart (нужен LM_ADMIN_PASSWORD в secrets/lm.env):"
echo "  curl -u \"\${LM_ADMIN_USER}:\${LM_ADMIN_PASSWORD}\" -H \"Referer: http://$HOST/apps/\" \\"
echo "    \"http://$HOST/apps/request.lp?action=stop&name=cottage-monitoring\""
