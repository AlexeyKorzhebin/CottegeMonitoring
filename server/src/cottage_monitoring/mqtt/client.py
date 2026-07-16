"""MQTT client wrapper with TLS, auth, auto-reconnect, persistent publisher."""

import asyncio
import ssl
from collections.abc import AsyncIterator

import aiomqtt
import structlog

logger = structlog.get_logger("cottage_monitoring.mqtt")


class MqttClient:
    """aiomqtt client wrapper with TLS, auth, and auto-reconnect."""

    def __init__(
        self,
        host: str,
        port: int = 1883,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = False,
        client_id: str | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._client_id = client_id
        self._topic: str | None = None
        self._connected = False
        self._backoff = 1.0
        self._shutdown = False
        self._pub_client: aiomqtt.Client | None = None
        self._pub_lock = asyncio.Lock()

    def _build_client_kwargs(self, *, for_publish: bool = False) -> dict:
        client_id = (self._client_id or "cottage-monitoring") + ("-pub" if for_publish else "")
        kwargs: dict = {
            "hostname": self._host,
            "port": self._port,
            "username": self._username,
            "password": self._password,
            "identifier": client_id,
        }
        if self._use_tls:
            ctx = ssl.create_default_context()
            kwargs["tls_context"] = ctx
        return kwargs

    async def connect(self) -> None:
        """Placeholder for connect. Connection is established in messages() loop."""
        pass

    async def disconnect(self) -> None:
        """Signal the messages() loop to stop on next reconnect cycle."""
        self._shutdown = True
        await self.stop_publisher()

    def subscribe(self, topic: str | list[str]) -> None:
        """Set topic(s) for subscription. Actual subscription happens in messages()."""
        self._topic = topic if isinstance(topic, list) else [topic]

    async def connect_and_subscribe(self, topic: str | list[str]) -> None:
        """Set topic for subscription. Connection established in messages() loop."""
        self.subscribe(topic)

    async def start_publisher(self) -> None:
        """Open a long-lived publish connection (separate client_id -pub)."""
        async with self._pub_lock:
            if self._pub_client is not None:
                return
            kwargs = self._build_client_kwargs(for_publish=True)
            client = aiomqtt.Client(**kwargs)
            await client.__aenter__()
            self._pub_client = client
            logger.info("mqtt_publisher_started", host=self._host, port=self._port)

    async def stop_publisher(self) -> None:
        """Close the persistent publisher if open."""
        async with self._pub_lock:
            if self._pub_client is None:
                return
            try:
                await self._pub_client.__aexit__(None, None, None)
            except Exception:
                logger.warning("mqtt_publisher_stop_error", exc_info=True)
            self._pub_client = None
            logger.info("mqtt_publisher_stopped")

    async def publish(self, topic: str, payload: str | bytes, qos: int = 1) -> None:
        """Publish via persistent publisher; reconnect once on failure."""
        async with self._pub_lock:
            if self._pub_client is None:
                kwargs = self._build_client_kwargs(for_publish=True)
                client = aiomqtt.Client(**kwargs)
                await client.__aenter__()
                self._pub_client = client
            try:
                await self._pub_client.publish(topic, payload, qos=qos)
                return
            except aiomqtt.MqttError:
                logger.warning("mqtt_publish_reconnect", topic=topic)
                try:
                    await self._pub_client.__aexit__(None, None, None)
                except Exception:
                    pass
                self._pub_client = None
                kwargs = self._build_client_kwargs(for_publish=True)
                client = aiomqtt.Client(**kwargs)
                await client.__aenter__()
                self._pub_client = client
                await self._pub_client.publish(topic, payload, qos=qos)

    async def messages(self) -> AsyncIterator[aiomqtt.Message]:
        """Async generator that yields messages with auto-reconnect on disconnect."""
        if not self._topic:
            raise ValueError(
                "Topic not set. Call subscribe(topic) or connect_and_subscribe(topic) first."
            )
        topics = self._topic if isinstance(self._topic, list) else [self._topic]

        while not self._shutdown:
            try:
                kwargs = self._build_client_kwargs()
                async with aiomqtt.Client(**kwargs) as client:
                    for t in topics:
                        await client.subscribe(t)
                    self._connected = True
                    self._backoff = 1.0
                    logger.info("mqtt_connected", host=self._host, port=self._port, topics=topics)
                    async for message in client.messages:
                        if self._shutdown:
                            break
                        yield message
            except aiomqtt.MqttError as e:
                self._connected = False
                logger.warning("mqtt_disconnected", error=str(e), reconnect_in=self._backoff)
                if self._shutdown:
                    return
                await asyncio.sleep(self._backoff)
                self._backoff = min(self._backoff * 2, 30.0)
            except asyncio.CancelledError:
                self._connected = False
                raise

        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Whether the client has an active connection (when inside messages() loop)."""
        return self._connected
