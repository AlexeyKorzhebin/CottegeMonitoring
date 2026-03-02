"""Redis cache wrapper for current state."""

import json
from typing import Any

import redis.asyncio as redis


class RedisCache:
    """Redis wrapper for caching house state data (HSET/HGET by house_id and ga)."""

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._client: redis.Redis | None = None

    async def connect(self) -> None:
        """Create Redis connection."""
        self._client = redis.Redis.from_url(self._redis_url, decode_responses=True)

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _key(self, house_id: str) -> str:
        return f"state:{house_id}"

    async def set_state(self, house_id: str, ga: str, data: dict[str, Any]) -> None:
        """HSET to key state:{house_id}, field {ga}, value JSON-serialized."""
        if not self._client:
            raise RuntimeError("Redis not connected. Call connect() first.")
        key = self._key(house_id)
        value = json.dumps(data)
        await self._client.hset(key, ga, value)

    async def get_state(self, house_id: str, ga: str) -> dict[str, Any] | None:
        """HGET from state:{house_id}, field {ga}. Returns dict or None."""
        if not self._client:
            raise RuntimeError("Redis not connected. Call connect() first.")
        key = self._key(house_id)
        value = await self._client.hget(key, ga)
        if value is None:
            return None
        return json.loads(value)

    async def get_all_states(self, house_id: str) -> dict[str, dict[str, Any]]:
        """HGETALL from state:{house_id}. Returns {ga: data_dict}."""
        if not self._client:
            raise RuntimeError("Redis not connected. Call connect() first.")
        key = self._key(house_id)
        raw = await self._client.hgetall(key)
        return {ga: json.loads(val) for ga, val in raw.items()}

    async def delete_state(self, house_id: str, ga: str) -> None:
        """HDEL from state:{house_id}, field {ga}."""
        if not self._client:
            raise RuntimeError("Redis not connected. Call connect() first.")
        key = self._key(house_id)
        await self._client.hdel(key, ga)

    @property
    def is_connected(self) -> bool:
        """Whether Redis connection is active."""
        return self._client is not None
