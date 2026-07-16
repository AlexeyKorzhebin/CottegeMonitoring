#!/usr/bin/env python3
"""Сводка operation_traces: MCP tools и command pipeline latency.

Usage:
  cd server && python scripts/trace_report.py
  cd server && python scripts/trace_report.py --minutes 60

Требуется DB_URL в .env / .env.test (dev БД). Для elion — SSH tunnel.
"""

from __future__ import annotations

import argparse
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


async def main(minutes: int) -> None:
    url = _get_conn_url()
    conn = await asyncpg.connect(url)
    try:
        exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'operation_traces')"
        )
        if not exists:
            print("Таблица operation_traces не найдена. Запустите: alembic upgrade head")
            return

        total = await conn.fetchval(
            "SELECT COUNT(*) FROM operation_traces WHERE ts > now() - ($1 || ' minutes')::interval",
            str(minutes),
        )
        print(f"=== OPERATION_TRACES (последние {minutes} мин) ===")
        print(f"  Всего записей: {total}")
        if not total:
            return

        by_kind = await conn.fetch(
            """
            SELECT kind,
                   COUNT(*) AS n,
                   ROUND(AVG(duration_ms)) AS avg_ms,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY duration_ms) AS p50_ms,
                   PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95_ms,
                   MAX(duration_ms) AS max_ms
            FROM operation_traces
            WHERE ts > now() - ($1 || ' minutes')::interval
              AND duration_ms IS NOT NULL
            GROUP BY kind
            ORDER BY kind
            """,
            str(minutes),
        )
        print("\n  По kind (duration_ms):")
        for r in by_kind:
            print(
                f"    {r['kind']:14} n={r['n']:4} avg={r['avg_ms']}ms "
                f"p50={r['p50_ms']}ms p95={r['p95_ms']}ms max={r['max_ms']}ms"
            )

        tools = await conn.fetch(
            """
            SELECT ref AS tool,
                   COUNT(*) AS n,
                   ROUND(AVG(duration_ms)) AS avg_ms,
                   MAX(duration_ms) AS max_ms
            FROM operation_traces
            WHERE ts > now() - ($1 || ' minutes')::interval
              AND kind = 'mcp_tool'
            GROUP BY ref
            ORDER BY n DESC
            LIMIT 15
            """,
            str(minutes),
        )
        if tools:
            print("\n  MCP tools:")
            for r in tools:
                print(f"    {r['tool']:22} n={r['n']:3} avg={r['avg_ms']}ms max={r['max_ms']}ms")

        recent = await conn.fetch(
            """
            SELECT ts, kind, ref, duration_ms, status, details
            FROM operation_traces
            WHERE ts > now() - ($1 || ' minutes')::interval
            ORDER BY ts DESC
            LIMIT 20
            """,
            str(minutes),
        )
        print("\n  Последние 20:")
        for r in recent:
            details = r["details"] or {}
            extra = ""
            if r["kind"] == "command_ack":
                extra = f" device={details.get('device_id', '?')}"
            elif r["kind"] == "command_sent":
                extra = f" items={details.get('item_count', '?')}"
            print(
                f"    {r['ts'].strftime('%H:%M:%S')} {r['kind']:14} "
                f"{r['ref'] or '-':36} {r['duration_ms'] or '-':>5}ms {r['status'] or ''}{extra}"
            )
    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=int, default=30)
    args = parser.parse_args()
    asyncio.run(main(args.minutes))
