"""Prometheus metrics for the MQTT ingestor."""

from prometheus_client import Counter, Gauge, Histogram

MESSAGES_TOTAL = Counter(
    "ingestor_messages_total",
    "Total MQTT messages processed",
    ["house_id", "message_type"],
)

LAG_SECONDS = Histogram(
    "ingestor_lag_seconds",
    "Ingestion lag in seconds",
    ["house_id"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

HOUSE_STATUS = Gauge(
    "ingestor_house_status",
    "House online status (1=online, 0=offline)",
    ["house_id"],
)

COMMAND_LATENCY = Histogram(
    "ingestor_command_latency_seconds",
    "Command round-trip latency",
    ["house_id"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
)

COMMAND_TIMEOUT_TOTAL = Counter(
    "ingestor_command_timeout_total",
    "Total command timeouts",
    ["house_id"],
)

SCHEMA_CHANGES_TOTAL = Counter(
    "ingestor_schema_changes_total",
    "Total schema changes detected",
    ["house_id"],
)

MQTT_RECONNECTS_TOTAL = Counter(
    "ingestor_mqtt_reconnects_total",
    "Total MQTT reconnections",
)
