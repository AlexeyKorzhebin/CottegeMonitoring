#!/usr/bin/env python3
"""Очистить все таблицы в dev-базе cottage_monitoring_dev.

Использует TRUNCATE CASCADE для безопасной очистки с учётом FK.
Порядок: events (hypertable, без FK) → houses CASCADE (затронет devices, objects,
current_state, schema_versions, commands).

Usage:
  cd server && python scripts/cleanup_dev_db.py

Требуется: .env или .env.test с DB_URL. Для удалённой БД — SSH-туннель (./server/scripts/tunnel-start.sh).
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Load env
_root = Path(__file__).resolve().parent.parent
for env_file in (_root / ".env.test", _root / ".env"):
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
            break
        except ImportError:
            break

try:
    import asyncpg
except ImportError:
    print("Requires asyncpg: pip install asyncpg", file=sys.stderr)
    sys.exit(1)


def _get_conn_url() -> str:
    url = os.environ.get("DB_URL", "")
    if not url:
        print("DB_URL not set. Use .env or .env.test, or export DB_URL=...", file=sys.stderr)
        sys.exit(1)
    # asyncpg expects postgresql://, not postgresql+asyncpg://
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def main() -> None:
    url = _get_conn_url()
    db_name = url.split("/")[-1].split("?")[0]
    if "cottage_monitoring_dev" not in db_name:
        print(f"WARNING: DB_URL points to '{db_name}', expected cottage_monitoring_dev.", file=sys.stderr)
        confirm = input("Continue anyway? [y/N]: ").strip().lower()
        if confirm != "y":
            sys.exit(1)

    print(f"Connecting to {db_name}...")
    conn = await asyncpg.connect(url)
    try:
        await conn.execute("TRUNCATE events, houses CASCADE;")
        print("Tables truncated: events, houses, devices, objects, current_state, schema_versions, commands")
        print("Done.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
