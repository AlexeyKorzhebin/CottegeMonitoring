#!/usr/bin/env bash
# Configure elion host services so Docker bridge containers can reach
# Postgres / Redis / Mosquitto via host.docker.internal (172.17.0.1).
# Does NOT open UFW public ports — only docker0 bridge.
#
# Run on elion: sudo bash server/deploy/elion-bind-docker0.sh
set -euo pipefail

DOCKER0_IP="${DOCKER0_IP:-172.17.0.1}"
DOCKER0_CIDR="${DOCKER0_CIDR:-172.17.0.0/16}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root (sudo)" >&2
  exit 1
fi

echo "== PostgreSQL: listen on localhost + ${DOCKER0_IP} =="
PG_CONF=$(echo /etc/postgresql/*/main/postgresql.conf)
PG_HBA=$(echo /etc/postgresql/*/main/pg_hba.conf)
# Uncomment/set listen_addresses
if grep -qE "^listen_addresses\s*=" "$PG_CONF"; then
  sed -i -E "s|^listen_addresses\s*=.*|listen_addresses = 'localhost,${DOCKER0_IP}'|" "$PG_CONF"
else
  sed -i -E "s|^#listen_addresses\s*=.*|listen_addresses = 'localhost,${DOCKER0_IP}'|" "$PG_CONF"
fi
if ! grep -qF "$DOCKER0_CIDR" "$PG_HBA"; then
  echo "host    all             all             ${DOCKER0_CIDR}           scram-sha-256" >>"$PG_HBA"
fi
systemctl reload postgresql || systemctl restart postgresql

echo "== Redis: bind localhost + ${DOCKER0_IP} =="
REDIS_CONF=/etc/redis/redis.conf
if grep -qE "^bind " "$REDIS_CONF"; then
  sed -i -E "s|^bind .*|bind 127.0.0.1 ::1 ${DOCKER0_IP}|" "$REDIS_CONF"
else
  echo "bind 127.0.0.1 ::1 ${DOCKER0_IP}" >>"$REDIS_CONF"
fi
systemctl restart redis-server

echo "== Mosquitto: listener 1883 on ${DOCKER0_IP} =="
MQ_CONF=/etc/mosquitto/conf.d/local-docker0.conf
cat >"$MQ_CONF" <<EOF
# Allow cottage-monitoring container (bridge) to reach local MQTT without TLS.
listener 1883 ${DOCKER0_IP}
protocol mqtt
allow_anonymous true
EOF
systemctl restart mosquitto

echo "== Docker hairpin: allow containers → host.docker.internal (172.17.0.1) =="
# Without route_localnet + INPUT accept, Linux/UFW drops container→gateway traffic.
cat >/etc/sysctl.d/99-cottage-docker-host-gateway.conf <<EOF
net.ipv4.conf.docker0.route_localnet=1
EOF
sysctl -p /etc/sysctl.d/99-cottage-docker-host-gateway.conf
# Prefer UFW application rule if available; always ensure iptables ACCEPT on docker0.
if command -v ufw >/dev/null 2>&1; then
  ufw allow in on docker0 to ${DOCKER0_IP} comment 'cottage docker host-gateway' || true
fi
iptables -C INPUT -i docker0 -d "${DOCKER0_IP}" -j ACCEPT 2>/dev/null \
  || iptables -I INPUT -i docker0 -d "${DOCKER0_IP}" -j ACCEPT
# Persist iptables rule across reboot (if netfilter-persistent installed)
if command -v netfilter-persistent >/dev/null 2>&1; then
  netfilter-persistent save || true
elif [[ -d /etc/iptables ]]; then
  iptables-save >/etc/iptables/rules.v4 || true
fi

echo "== verify listeners =="
ss -tlnp | grep -E ":5432|:6379|:1883" || true
echo "OK: host deps bound for docker0 (${DOCKER0_IP})"
