#!/usr/bin/env python3
"""Create a scoped API key for MCP/agent access."""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

from cottage_monitoring.auth.keys import generate_api_key, hash_api_key
from cottage_monitoring.db.session import async_session_factory
from cottage_monitoring.models.api_key import ApiKey
from cottage_monitoring.services.house_service import ensure_house


async def main() -> int:
    parser = argparse.ArgumentParser(description="Create CottageMonitoring API key")
    parser.add_argument("--house", required=True, help="house_id")
    parser.add_argument("--name", required=True, help="Human-readable key name")
    parser.add_argument(
        "--scopes",
        default="read,write",
        help="Comma-separated scopes (read, write)",
    )
    args = parser.parse_args()
    scopes = [s.strip() for s in args.scopes.split(",") if s.strip()]
    if not scopes:
        print("At least one scope required", file=sys.stderr)
        return 1

    raw, prefix = generate_api_key()
    async with async_session_factory() as session:
        await ensure_house(args.house, session=session)
        row = ApiKey(
            id=uuid.uuid4(),
            name=args.name,
            key_prefix=prefix,
            key_hash=hash_api_key(raw),
            house_id=args.house,
            scopes=scopes,
        )
        session.add(row)
        await session.commit()

    print(f"house_id={args.house}")
    print(f"scopes={','.join(scopes)}")
    print(f"api_key={raw}")
    print("Store the api_key securely — it will not be shown again.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
