# Platform metrics receiver

Disabled by default. Configure `PLATFORM_METRICS_ENABLED=true`, a protected `PLATFORM_METRICS_TOKEN_FILE` (one random bearer token), and `PLATFORM_METRICS_DB_URL` (a separate `postgresql+asyncpg` writer login). Keep secrets outside Git and logs. Restart on DSN rotation; token file is read per request. Never use the household database login as writer.

SQL files are operator-reviewed deployment artifacts and have not been applied. Provision owner, writer, reader, maintenance roles and database CONNECT separately, then apply schema and grants with an administrator. Inspect PUBLIC and inherited grants; verify allowed and forbidden operations using actual roles. Grant reader access to the actual Grafana role only after verifying it. Schedule bounded cleanup as a single non-overlapping job and monitor failures and storage. Review backups before rollback.

The application applies a per-process token bucket (60/minute, burst 10); a shared frontend limit is required across multiple workers. Configure the existing HTTPS frontend for the exact route with 64 KiB limit, equivalent shared rate limiting, short timeouts and no body or Authorization logging. Verify actual vhost, TLS, logging and service deployment separately; no live configuration is modified here.

## Local PostgreSQL integration evidence (2026-11-13)

`PM_PG_FIXTURE=1 server/.venv/bin/python -m pytest server/tests/integration/test_platform_metrics_postgres.py -q` passed against the locally cached pinned `postgres:16.10-alpine` image on Docker `desktop-linux`. The test creates one randomly named loopback-only container with one CPU and 384 MiB limits, fixture-only random credentials, and removes its container and anonymous volume afterwards. It exercises the migration and grants, accepted/duplicate/conflict HTTP responses, concurrent duplicate insert, transactional rollback, denial of writer DDL/DELETE/household insert, maintenance cleanup and schema rollback while preserving a household fixture row. The cleanup test caught and corrected a permission mismatch: a single non-overlapping cleanup job is required.

This is a local fixture, not proof of production roles, inherited/PUBLIC privileges, concurrent cleanup, live TLS or proxy limits, backup/restore, production migrations, or deployment behavior. Docker must have the pinned image cached; the test never pulls it.
