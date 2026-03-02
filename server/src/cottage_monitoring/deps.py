"""Shared application dependencies: Redis cache, MQTT client instances."""

from cottage_monitoring.config import settings
from cottage_monitoring.mqtt.client import MqttClient
from cottage_monitoring.services.redis_cache import RedisCache

redis_cache = RedisCache(settings.redis_url)

mqtt_client = MqttClient(
    host=settings.mqtt_host,
    port=settings.mqtt_port,
    username=settings.mqtt_user,
    password=settings.mqtt_password,
    use_tls=settings.mqtt_use_tls,
    client_id=settings.mqtt_client_id,
)
