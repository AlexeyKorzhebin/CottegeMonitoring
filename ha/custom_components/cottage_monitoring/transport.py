import aiohttp


class AiohttpTransport:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def __call__(self, method, url, headers, json):
        timeout = aiohttp.ClientTimeout(total=20)
        async with self._session.request(
            method, url, headers=headers, json=json, timeout=timeout
        ) as resp:
            try:
                payload = await resp.json()
            except Exception:
                payload = await resp.text()
            return resp.status, payload
