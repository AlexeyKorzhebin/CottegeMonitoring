#!/bin/sh
# HA-managed go2rtc hardcodes webrtc listen ":18555/tcp" (all interfaces).
# Bind loopback so host-network Container does not expose WebRTC publicly.
f=/usr/src/homeassistant/homeassistant/components/go2rtc/server.py
if [ -f "$f" ]; then
  sed -i 's|listen: ":18555/tcp"|listen: "127.0.0.1:18555/tcp"|' "$f" || true
fi
exec /init
