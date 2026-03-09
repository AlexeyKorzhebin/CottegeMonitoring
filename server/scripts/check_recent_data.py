#!/usr/bin/env python3
"""Проверка последних записей в БД: events, current_state.

Usage:
  cd server && python scripts/check_recent_data.py

Требуется: .env или .env.test с DB_URL. Для удалённой БД — SSH tunnel.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

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
        print("DB_URL not set. Use .env or .env.test", file=sys.stderr)
        sys.exit(1)
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def main() -> None:
    url = _get_conn_url()
    conn = await asyncpg.connect(url)
    try:
        # Events: последние записи
        events_info = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total,
                MAX(ts) as last_ts,
                MAX(server_received_ts) as last_received,
                MAX(house_id) as sample_house,
                MAX(device_id) as sample_device
            FROM events
        """)
        print("=== EVENTS ===")
        if events_info and events_info["total"] and int(events_info["total"]) > 0:
            print(f"  Всего записей: {events_info['total']}")
            print(f"  Последняя ts (время с устройства): {events_info['last_ts']}")
            print(f"  Последняя server_received_ts:     {events_info['last_received']}")
            print(f"  Дом: {events_info['sample_house']}, устройство: {events_info['sample_device']}")

            # Последние 3 события
            rows = await conn.fetch("""
                SELECT house_id, device_id, ga, ts, value, server_received_ts
                FROM events ORDER BY ts DESC LIMIT 3
            """)
            print("  Последние 3 события:")
            for r in rows:
                print(f"    {r['ts']} | house={r['house_id']} dev={r['device_id']} ga={r['ga']} val={r['value']}")
        else:
            print("  Нет записей.")

        # Current_state: последние обновления
        state_info = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total,
                MAX(ts) as last_ts,
                MAX(server_received_ts) as last_received
            FROM current_state
        """)
        print("\n=== CURRENT_STATE ===")
        if state_info and state_info["total"] and int(state_info["total"]) > 0:
            print(f"  Всего GA: {state_info['total']}")
            print(f"  Последнее обновление ts:         {state_info['last_ts']}")
            print(f"  Последнее server_received_ts:    {state_info['last_received']}")

            rows = await conn.fetch("""
                SELECT house_id, ga, device_id, ts, value, server_received_ts
                FROM current_state ORDER BY server_received_ts DESC LIMIT 3
            """)
            print("  Последние 3 обновления:")
            for r in rows:
                print(f"    {r['server_received_ts']} | house={r['house_id']} ga={r['ga']} val={r['value']}")
        else:
            print("  Нет записей.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
