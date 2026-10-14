# Status-topic compatibility patch — 2026-10-14

Production 0.3.5 already accepts status/offline but canonical main 0.3.4 does not. The old /opt checkout is 0.1.0 and is not a deployment source. Preserve live 0.3.5 through an immutable base image and replace only dispatcher/parser; do not downgrade unrelated features.

Health is recognized JSON diagnostics and intentionally ignored before registry/last_seen writes. Retained replay must never imply fresh sensor telemetry. Online/offline payload handling and Grafana stale alert remain unchanged. Unexpected status subtopics still warn.

Base preflight: verify image ID 270d3e5dac6ade853a607c513451d9f88eb19caef8d507121c42f2916c530660 and tag it as cottage-monitoring:status-topics-base-270d3e5dac6a. BuildKit cannot use a local raw image ID in FROM.

Build from server: docker build -f deploy/status-topics/Dockerfile -t cottage-monitoring:0.3.5-status-topics-20261014 .
Rollback: restore systemd production image tag cottage-monitoring:0.3.5, daemon-reload, restart and verify /health. Original unit is backed up outside systemd config. The base/ folder contains the exact production files used for comparison.

## Retained status replay repair — 2026-10-14

The client creates its LWT timestamp at connection setup (daemon.lua: will_set),
so comparing online/offline payload timestamps would discard a real later live
will. Instead, ignore broker-retained online/offline before any registry writes.
Accept live transitions in broker delivery order. After successful ingestion,
non-retained sensor events with GA/value and a finite numeric device timestamp
within 120 seconds (maximum future skew 30 seconds) recover an offline device.
Old queued events, health and retained messages cannot establish recovery.
No events means no invented recovery: the existing stale-device sweep and
Grafana >15m alert remain effective, including offline during ingestor downtime.
A house without fresh sensor events remains conservative until live evidence.

Regression: both retained delivery orders, prod/dev prefixes, restart replay,
fresh recovery, live LWT with connection-time timestamp, stale events and
invalid/future timestamps. 35 focused tests passed, with no production writes.
Build from server: docker build -f deploy/status-topics/Dockerfile -t cottage-monitoring:0.3.5-status-replay-20261014 .
Rollback: restore the backed-up pre-repair systemd unit pointing at
cottage-monitoring:0.3.5-status-topics-20261014; daemon-reload and restart.
