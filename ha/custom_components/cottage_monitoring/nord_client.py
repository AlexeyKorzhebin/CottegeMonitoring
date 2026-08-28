from __future__ import annotations


class NordError(Exception):
    def __init__(self, status: int, body: str):
        self.status = status
        self.body = body


class NordClient:
    def __init__(self, base_url: str, api_key: str, house_id: str, *, transport=None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.house_id = house_id
        self._transport = transport  # async callable(method, url, headers, json) -> tuple[int, dict|str]

    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self.api_key, "Content-Type": "application/json"}

    async def call_op(self, name: str, body: dict | None = None) -> dict:
        url = f"{self.base_url}/houses/{self.house_id}/ops/{name}"
        status, payload = await self._transport("POST", url, self._headers(), body or {})
        if status in (401, 403):
            raise NordError(status, str(payload))
        if status == 429:
            raise NordError(status, str(payload))
        if status >= 500 or status == 0:
            raise NordError(status, str(payload))
        if not isinstance(payload, dict):
            raise NordError(status, str(payload))
        return payload
