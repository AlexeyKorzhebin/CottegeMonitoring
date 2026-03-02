from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "", "env_file": ".env", "extra": "ignore"}

    env: str = "dev"

    # Database
    db_url: str = "postgresql+asyncpg://cottage:cottage@localhost:5432/cottage_monitoring_dev"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # MQTT
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_user: str | None = None
    mqtt_password: str | None = None
    mqtt_use_tls: bool = False
    mqtt_client_id: str = "cottage-monitoring-server"
    mqtt_topic_prefix: str = ""

    # API
    api_port: int = 8321
    api_host: str = "0.0.0.0"

    # Logging
    log_level: str = "INFO"
    log_dir: str = "/var/log/cottage-monitoring"
    log_max_bytes: int = 52_428_800  # 50 MB
    log_backup_count: int = 10

    # Commands
    cmd_timeout_seconds: int = 60
    cmd_max_retries: int = 2

    @property
    def mqtt_subscription_topic(self) -> str:
        return f"{self.mqtt_topic_prefix}cm/+/+/v1/#"


settings = Settings()
