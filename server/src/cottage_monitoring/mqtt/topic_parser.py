"""MQTT topic parser for CottageMonitoring namespace.

Parses topics in format: {prefix}cm/<house_id>/<device_id>/v1/<rest...>
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class MessageType(Enum):
    """Message type inferred from topic's rest segment."""

    EVENT = "event"
    EVENT_BATCH = "event_batch"
    STATE = "state"
    STATE_BATCH = "state_batch"
    META_FULL = "meta_full"
    META_CHUNK = "meta_chunk"
    STATUS = "status"
    CMD_ACK = "cmd_ack"
    RPC_RESP = "rpc_resp"


@dataclass
class ParsedTopic:
    """Result of topic parsing."""

    house_id: str
    device_id: str
    message_type: MessageType
    params: dict


def parse_topic(topic: str, prefix: str = "") -> ParsedTopic | None:
    """Parse MQTT topic into structured form.

    Strips the configurable prefix (e.g. empty or "dev/") from the start,
    then parses the remainder as cm/<house_id>/<device_id>/v1/<rest>.

    Args:
        topic: Raw MQTT topic string.
        prefix: Optional prefix to strip (e.g. "" or "dev/").

    Returns:
        ParsedTopic with house_id, device_id, message_type, params;
        or None if unparseable.
    """
    if prefix:
        if not topic.startswith(prefix):
            return None
        topic = topic[len(prefix) :]

    parts = topic.split("/")
    if len(parts) < 5:
        return None
    if parts[0] != "cm" or parts[3] != "v1":
        return None

    house_id = parts[1]
    device_id = parts[2]
    rest = "/".join(parts[4:])

    if rest == "events":
        return ParsedTopic(house_id=house_id, device_id=device_id, message_type=MessageType.EVENT, params={})

    if rest == "events/batch":
        return ParsedTopic(house_id=house_id, device_id=device_id, message_type=MessageType.EVENT_BATCH, params={})

    if rest == "state/batch":
        return ParsedTopic(house_id=house_id, device_id=device_id, message_type=MessageType.STATE_BATCH, params={})

    if rest.startswith("state/ga/"):
        ga = rest[len("state/ga/") :]
        return ParsedTopic(house_id=house_id, device_id=device_id, message_type=MessageType.STATE, params={"ga": ga})

    if rest.startswith("meta/objects/chunk/"):
        chunk_part = rest[len("meta/objects/chunk/") :]
        try:
            chunk_no = int(chunk_part)
            return ParsedTopic(house_id=house_id, device_id=device_id, message_type=MessageType.META_CHUNK, params={"chunk_no": chunk_no})
        except ValueError:
            return None

    if rest == "meta/objects":
        return ParsedTopic(house_id=house_id, device_id=device_id, message_type=MessageType.META_FULL, params={})

    if rest == "status/online":
        return ParsedTopic(house_id=house_id, device_id=device_id, message_type=MessageType.STATUS, params={})

    if rest.startswith("cmd/ack/"):
        request_id = rest[len("cmd/ack/") :]
        return ParsedTopic(house_id=house_id, device_id=device_id, message_type=MessageType.CMD_ACK, params={"request_id": request_id})

    if rest.startswith("rpc/resp/"):
        subparts = rest[len("rpc/resp/") :].split("/")
        if len(subparts) >= 2:
            client_id = subparts[0]
            request_id = subparts[1]
            return ParsedTopic(
                house_id=house_id,
                device_id=device_id,
                message_type=MessageType.RPC_RESP,
                params={"client_id": client_id, "request_id": request_id},
            )
        return None

    return None
