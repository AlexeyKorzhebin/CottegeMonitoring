#!/usr/bin/env python3
"""Clear retained MQTT messages on dev/ and test/ topics.

Subscribes to dev/# and test/#, receives retained messages (broker sends on subscribe),
then publishes empty payload with retain=True to each topic to clear them.

Usage:
  cd server && python scripts/cleanup_mqtt_topics.py

Requires: .env or .env.test with MQTT_HOST, MQTT_PORT. SSH tunnel to elion for remote broker.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

# Load env
_root = Path(__file__).resolve().parent.parent
for env_file in (_root / ".env.test", _root / ".env"):
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file)
        break

import aiomqtt


async def main() -> None:
    host = os.environ.get("MQTT_HOST", "localhost")
    port = int(os.environ.get("MQTT_PORT", "1883"))
    topics_to_clear: set[str] = set()

    print(f"Connecting to {host}:{port}...")
    async with aiomqtt.Client(hostname=host, port=port) as client:
        for pattern in ("dev/#", "test/#"):
            await client.subscribe(pattern)
            print(f"Subscribed to {pattern}, waiting for retained messages (3s)...")

        async def collect_retained() -> None:
            async for msg in client.messages:
                topic = str(msg.topic)
                if msg.retain:
                    topics_to_clear.add(topic)

        try:
            await asyncio.wait_for(collect_retained(), timeout=5.0)
        except asyncio.TimeoutError:
            pass

    if not topics_to_clear:
        print("No retained messages found on dev/ or test/.")
        return

    print(f"Found {len(topics_to_clear)} retained topic(s). Clearing...")
    async with aiomqtt.Client(hostname=host, port=port) as client:
        for topic in sorted(topics_to_clear):
            await client.publish(topic, b"", retain=True)
            print(f"  cleared {topic}")

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
