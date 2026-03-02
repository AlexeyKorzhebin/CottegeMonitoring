"""MQTT client wrapper with TLS, auth, auto-reconnect."""

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

    def _build_client_kwargs(self) -> dict:
        kwargs: dict = {
            "hostname": self._host,
            "port": self._port,
            "username": self._username,
            "password": self._password,
            "identifier": self._client_id,
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

    def subscribe(self, topic: str) -> None:
        """Set topic for subscription. Actual subscription happens in messages()."""
        self._topic = topic

    async def connect_and_subscribe(self, topic: str) -> None:
        """Set topic for subscription. Connection established in messages() loop."""
        self.subscribe(topic)

    async def publish(self, topic: str, payload: str | bytes, qos: int = 1) -> None:
        """Publish message. Opens a new connection per call."""
        kwargs = self._build_client_kwargs()
        async with aiomqtt.Client(**kwargs) as client:
            await client.publish(topic, payload, qos=qos)

    async def messages(self) -> AsyncIterator[aiomqtt.Message]:
        """Async generator that yields messages with auto-reconnect on disconnect."""
        if not self._topic:
            raise ValueError(
                "Topic not set. Call subscribe(topic) or connect_and_subscribe(topic) first."
            )
        topic = self._topic

        while not self._shutdown:
            try:
                kwargs = self._build_client_kwargs()
                async with aiomqtt.Client(**kwargs) as client:
                    await client.subscribe(topic)
                    self._connected = True
                    self._backoff = 1.0
                    logger.info("mqtt_connected", host=self._host, port=self._port, topic=topic)
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
