"""Unit tests for application config (Settings)."""

from cottage_monitoring.config import Settings


class TestSettingsDefaults:
    """Test default values are set correctly."""

    def test_db_url_default(self):
        s = Settings()
        expected = "postgresql+asyncpg://cottage:cottage@localhost:5432/cottage_monitoring_dev"
        assert s.db_url == expected

    def test_redis_url_default(self):
        s = Settings()
        assert s.redis_url == "redis://localhost:6379/0"

    def test_mqtt_defaults(self):
        s = Settings()
        assert s.mqtt_host == "localhost"
        assert s.mqtt_port == 1883
        assert s.mqtt_user is None
        assert s.mqtt_password is None
        assert s.mqtt_use_tls is False
        assert s.mqtt_client_id == "cottage-monitoring-server"
        assert s.mqtt_topic_prefix == ""

    def test_api_defaults(self):
        s = Settings()
        assert s.api_port == 8321
        assert s.api_host == "0.0.0.0"

    def test_logging_defaults(self):
        s = Settings()
        assert s.log_level == "INFO"
        assert s.log_dir == "/var/log/cottage-monitoring"


class TestMqttSubscriptionTopic:
    """Test mqtt_subscription_topic property."""

    def test_empty_prefix(self):
        s = Settings()
        assert s.mqtt_subscription_topic == "lm/+/v1/#"

    def test_dev_prefix(self, monkeypatch):
        monkeypatch.setenv("MQTT_TOPIC_PREFIX", "dev/")
        s = Settings()
        assert s.mqtt_subscription_topic == "dev/lm/+/v1/#"


class TestSettingsFromEnv:
    """Test config reads from environment variables."""

    def test_db_url_from_env(self, monkeypatch):
        monkeypatch.setenv("DB_URL", "postgresql+asyncpg://test:test@db:5432/test")
        s = Settings()
        assert s.db_url == "postgresql+asyncpg://test:test@db:5432/test"

    def test_redis_url_from_env(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://redis:6379/1")
        s = Settings()
        assert s.redis_url == "redis://redis:6379/1"

    def test_mqtt_host_from_env(self, monkeypatch):
        monkeypatch.setenv("MQTT_HOST", "mqtt.example.com")
        s = Settings()
        assert s.mqtt_host == "mqtt.example.com"

    def test_mqtt_topic_prefix_from_env(self, monkeypatch):
        monkeypatch.setenv("MQTT_TOPIC_PREFIX", "dev/")
        s = Settings()
        assert s.mqtt_topic_prefix == "dev/"


class TestSettingsTypeCoercion:
    """Test type coercion for env vars."""

    def test_mqtt_port_string_to_int(self, monkeypatch):
        monkeypatch.setenv("MQTT_PORT", "1883")
        s = Settings()
        assert s.mqtt_port == 1883
        assert isinstance(s.mqtt_port, int)

    def test_mqtt_use_tls_string_to_bool(self, monkeypatch):
        monkeypatch.setenv("MQTT_USE_TLS", "true")
        s = Settings()
        assert s.mqtt_use_tls is True
        assert isinstance(s.mqtt_use_tls, bool)
