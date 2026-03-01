"""MQTT message dispatcher — routes messages to appropriate services."""

from __future__ import annotations

import json

import aiomqtt
import structlog

from cottage_monitoring.config import settings
from cottage_monitoring.mqtt.topic_parser import MessageType, parse_topic

logger = structlog.get_logger(__name__)


async def handle_message(message: aiomqtt.Message) -> None:
    """Parse MQTT topic and dispatch to the correct service handler."""
    topic_str = str(message.topic)
    parsed = parse_topic(topic_str, prefix=settings.mqtt_topic_prefix)
    if parsed is None:
        logger.warning("unknown_topic", topic=topic_str)
        return

    try:
        payload = json.loads(message.payload)
    except (json.JSONDecodeError, TypeError):
        logger.warning("invalid_json", topic=topic_str)
        return

    house_id = parsed.house_id
    msg_type = parsed.message_type

    from cottage_monitoring.metrics import MESSAGES_TOTAL

    MESSAGES_TOTAL.labels(house_id=house_id, message_type=msg_type.value).inc()

    from cottage_monitoring.services.house_service import ensure_house, is_house_active

    await ensure_house(house_id)

    # Skip processing for deactivated houses (except status updates)
    if msg_type != MessageType.STATUS:
        active = await is_house_active(house_id)
        if not active:
            logger.warning("message_for_inactive_house", house_id=house_id, message_type=msg_type.value)
            return

    if msg_type == MessageType.STATE:
        from cottage_monitoring.services.state_service import handle_state

        await handle_state(house_id, parsed.params["ga"], payload)
    elif msg_type == MessageType.EVENT:
        from cottage_monitoring.services.event_service import handle_event

        await handle_event(house_id, payload)
    elif msg_type == MessageType.META_FULL:
        from cottage_monitoring.services.schema_service import handle_full_meta

        await handle_full_meta(house_id, payload)
    elif msg_type == MessageType.META_CHUNK:
        from cottage_monitoring.services.schema_service import handle_chunk_meta

        await handle_chunk_meta(house_id, parsed.params["chunk_no"], payload)
    elif msg_type == MessageType.STATUS:
        from cottage_monitoring.services.house_service import handle_status

        await handle_status(house_id, payload)
    elif msg_type == MessageType.CMD_ACK:
        from cottage_monitoring.services.command_service import handle_ack

        await handle_ack(house_id, parsed.params["request_id"], payload)
    elif msg_type == MessageType.RPC_RESP:
        from cottage_monitoring.services.rpc_service import handle_rpc_response

        await handle_rpc_response(
            house_id, parsed.params["client_id"], parsed.params["request_id"], payload
        )

    logger.debug(
        "message_processed", house_id=house_id, message_type=msg_type.value, topic=topic_str
    )
