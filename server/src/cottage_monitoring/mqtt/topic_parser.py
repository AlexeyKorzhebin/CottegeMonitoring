"""MQTT topic parser for LogicMachine namespace.

Parses topics in format: {prefix}lm/<house_id>/v1/<rest...>
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class MessageType(Enum):
    """Message type inferred from topic's rest segment."""

    EVENT = "event"
    STATE = "state"
    META_FULL = "meta_full"
    META_CHUNK = "meta_chunk"
    STATUS = "status"
    CMD_ACK = "cmd_ack"
    RPC_RESP = "rpc_resp"


@dataclass
class ParsedTopic:
    """Result of topic parsing."""

    house_id: str
    message_type: MessageType
    params: dict


def parse_topic(topic: str, prefix: str = "") -> ParsedTopic | None:
    """Parse MQTT topic into structured form.

    Strips the configurable prefix (e.g. empty or "dev/") from the start,
    then parses the remainder as lm/<house_id>/v1/<rest>.

    Args:
        topic: Raw MQTT topic string.
        prefix: Optional prefix to strip (e.g. "" or "dev/").

    Returns:
        ParsedTopic with house_id, message_type, params; or None if unparseable.
    """
    # Strip prefix
    if prefix:
        if not topic.startswith(prefix):
            return None
        topic = topic[len(prefix) :]

    # Parse lm/<house_id>/v1/<rest>
    parts = topic.split("/")
    if len(parts) < 4:
        return None
    if parts[0] != "lm" or parts[2] != "v1":
        return None

    house_id = parts[1]
    rest = "/".join(parts[3:])

    # Match rest (order matters: more specific patterns before generic)
    if rest == "events":
        return ParsedTopic(house_id=house_id, message_type=MessageType.EVENT, params={})

    if rest.startswith("state/ga/"):
        ga = rest[len("state/ga/") :]
        return ParsedTopic(house_id=house_id, message_type=MessageType.STATE, params={"ga": ga})

    if rest.startswith("meta/objects/chunk/"):
        chunk_part = rest[len("meta/objects/chunk/") :]
        try:
            chunk_no = int(chunk_part)
            return ParsedTopic(house_id=house_id, message_type=MessageType.META_CHUNK, params={"chunk_no": chunk_no})
        except ValueError:
            return None

    if rest == "meta/objects":
        return ParsedTopic(house_id=house_id, message_type=MessageType.META_FULL, params={})

    if rest == "status/online":
        return ParsedTopic(house_id=house_id, message_type=MessageType.STATUS, params={})

    if rest.startswith("cmd/ack/"):
        request_id = rest[len("cmd/ack/") :]
        return ParsedTopic(house_id=house_id, message_type=MessageType.CMD_ACK, params={"request_id": request_id})

    if rest.startswith("rpc/resp/"):
        subparts = rest[len("rpc/resp/") :].split("/")
        if len(subparts) >= 2:
            client_id = subparts[0]
            request_id = subparts[1]
            return ParsedTopic(
                house_id=house_id,
                message_type=MessageType.RPC_RESP,
                params={"client_id": client_id, "request_id": request_id},
            )
        return None

    return None
