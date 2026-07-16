#!/usr/bin/env bash
# Deploy CottageMonitoring Grafana datasource + dashboards to elion.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "== generate dashboards =="
python3 "$ROOT/generate_dashboards.py"

echo "== ensure remote staging dir =="
ssh elion 'mkdir -p /tmp/cottage-grafana-dashboards'
scp "$ROOT"/dashboards/cottage_*.json \
  "$ROOT/provisioning/dashboards/cottage_dashboards.yaml" \
  elion:/tmp/cottage-grafana-dashboards/

echo "== remote install =="
ssh elion 'bash -s' <<'REMOTE'
set -euo pipefail

PASS_FILE=/etc/cottage-monitoring/grafana-db.password
sudo mkdir -p /etc/cottage-monitoring
if [[ ! -f "$PASS_FILE" ]]; then
  openssl rand -base64 24 | sudo tee "$PASS_FILE" >/dev/null
  sudo chmod 640 "$PASS_FILE"
fi
# readable by root for this script
PASS=$(sudo cat "$PASS_FILE")

echo "== DB role cottage_grafana =="
# Escape single quotes for SQL password literal
PASS_SQL=${PASS//\'/\'\'}
sudo -u postgres psql -v ON_ERROR_STOP=1 -d cottage_monitoring <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'cottage_grafana') THEN
    CREATE ROLE cottage_grafana LOGIN PASSWORD '${PASS_SQL}';
  ELSE
    ALTER ROLE cottage_grafana WITH LOGIN PASSWORD '${PASS_SQL}';
  END IF;
END
\$\$;
GRANT CONNECT ON DATABASE cottage_monitoring TO cottage_grafana;
GRANT USAGE ON SCHEMA public TO cottage_grafana;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO cottage_grafana;
ALTER DEFAULT PRIVILEGES FOR ROLE cottage IN SCHEMA public GRANT SELECT ON TABLES TO cottage_grafana;
SQL

echo "== datasource provisioning =="
sudo mkdir -p /etc/grafana/provisioning/datasources /etc/grafana/provisioning/dashboards
sudo tee /etc/grafana/provisioning/datasources/cottage_monitoring.yaml >/dev/null <<YAML
apiVersion: 1

datasources:
  - name: Cottage Monitoring
    uid: cottage-monitoring-pg
    type: postgres
    access: proxy
    url: 127.0.0.1:5432
    user: cottage_grafana
    isDefault: false
    editable: false
    jsonData:
      database: cottage_monitoring
      sslmode: disable
      postgresVersion: 1600
      timescaledb: true
    secureJsonData:
      password: "${PASS}"
YAML

sudo install -m 644 /tmp/cottage-grafana-dashboards/cottage_dashboards.yaml \
  /etc/grafana/provisioning/dashboards/cottage_dashboards.yaml

echo "== dashboards =="
sudo mkdir -p /var/lib/grafana/dashboards/cottage
sudo install -o grafana -g grafana -m 644 \
  /tmp/cottage-grafana-dashboards/cottage_*.json \
  /var/lib/grafana/dashboards/cottage/

echo "== reload grafana =="
sudo systemctl restart grafana-server
sleep 3
systemctl is-active grafana-server

# Verify DB login
PGPASSWORD="$PASS" psql -h 127.0.0.1 -U cottage_grafana -d cottage_monitoring -c \
  "SELECT count(*) AS states FROM current_state WHERE house_id='house';"

ls -la /var/lib/grafana/dashboards/cottage/
echo "OK: Cottage Grafana dashboards deployed"
REMOTE
