#!/usr/bin/env bash
# Deploy cm-client to LogicMachine controller via lftp (FTP).
# Usage: ./deploy-lftp.sh [host] [user] [password]
# Example: ./deploy-lftp.sh 192.168.100.130 apps <password>
# Default: ftp://apps@192.168.100.130 per quickstart.md

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCE_DIR="$PROJECT_ROOT/cm-client"

# LM: user "apps" — FTP root может быть store ИЛИ data/cottage-monitoring (app dir)
# store: нужно cd data/cottage-monitoring
# app dir: уже в правильной папке, mirror в .
REMOTE_APP_PATH="data/cottage-monitoring"
REMOTE_DAEMON_PATH="daemon/cottage-monitoring"

HOST="${1:-192.168.100.130}"
USER="${2:-apps}"
PASS="${3:-}"

if [ -z "$PASS" ]; then
  echo "Usage: $0 <host> <user> <password>"
  echo "Default host: 192.168.100.130, user: apps"
  exit 1
fi

cd "$SOURCE_DIR"

# 1. Приложение: пробуем data/cottage-monitoring; при ошибке — текущая папка (app dir)
echo "Uploading app to $REMOTE_APP_PATH..."
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

# 2. Daemon в daemon/cottage-monitoring (per LM docs: "Create new directory named as
#    your application in daemon directory. Place daemon.lua inside newly created directory")
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

# 3. Проверка: список загруженных файлов (для отладки пути)
echo ""
echo "Verify — files in $REMOTE_APP_PATH:"
lftp -u "$USER","$PASS" "ftp://$HOST" -e "
cd $REMOTE_APP_PATH
cls -1
bye
" 2>/dev/null || lftp -u "$USER","$PASS" "ftp://$HOST" -e "cls -1" 2>/dev/null

echo ""
echo "Deployed. App URL: http://$HOST/apps/data/cottage-monitoring/"
