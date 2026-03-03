#!/usr/bin/env bash
# Deploy cm-client to LogicMachine controller via lftp (FTP).
# Usage: ./deploy-lftp.sh [host] [user] [password]
# Example: ./deploy-lftp.sh 192.168.100.130 apps <password>
# Default: ftp://apps@192.168.100.130 per quickstart.md

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCE_DIR="$PROJECT_ROOT/cm-client"
REMOTE_PATH="/data/apps/store/data/cottage-monitoring"

HOST="${1:-192.168.100.130}"
USER="${2:-apps}"
PASS="${3:-}"

if [ -z "$PASS" ]; then
  echo "Usage: $0 <host> <user> <password>"
  echo "Default host: 192.168.100.130, user: apps"
  exit 1
fi

cd "$SOURCE_DIR"
lftp -u "$USER","$PASS" "ftp://$HOST" -e "
cd $REMOTE_PATH
lcd $SOURCE_DIR
mirror -R .
bye
"

echo "Deployed to ftp://$USER@$HOST$REMOTE_PATH"
