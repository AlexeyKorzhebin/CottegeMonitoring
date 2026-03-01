"""RPC service: request/response for meta and snapshot via MQTT."""

from __future__ import annotations

import json
import uuid

import structlog

from cottage_monitoring.config import settings
from cottage_monitoring.deps import mqtt_client

logger = structlog.get_logger(__name__)

# Pending RPC requests: {request_id: {"chunks": {...}, "chunk_total": N, ...}}
_pending_rpc: dict[str, dict] = {}


async def request_meta(house_id: str) -> str:
    """Send RPC request for meta/objects. Returns request_id."""
    return await _send_rpc(house_id, "meta")


async def request_snapshot(house_id: str) -> str:
    """Send RPC request for snapshot. Returns request_id."""
    return await _send_rpc(house_id, "snapshot")


async def _send_rpc(house_id: str, method: str) -> str:
    request_id = str(uuid.uuid4())
    client_id = settings.mqtt_client_id
    topic = f"{settings.mqtt_topic_prefix}lm/{house_id}/v1/rpc/req/{client_id}"
    payload = {"request_id": request_id, "method": method, "params": {"scope": "all"}}
    await mqtt_client.publish(topic, json.dumps(payload))
    _pending_rpc[request_id] = {"method": method, "chunks": {}, "chunk_total": None}
    logger.info("rpc_request_sent", house_id=house_id, method=method, request_id=request_id)
    return request_id


async def handle_rpc_response(
    house_id: str, client_id: str, request_id: str, payload: dict
) -> None:
    """Handle rpc/resp — assemble chunked responses."""
    chunk_no = payload.get("chunk_no", 1)
    chunk_total = payload.get("chunk_total", 1)

    if request_id not in _pending_rpc:
        _pending_rpc[request_id] = {"chunks": {}, "chunk_total": chunk_total}

    _pending_rpc[request_id]["chunks"][chunk_no] = payload.get("result", {})
    _pending_rpc[request_id]["chunk_total"] = chunk_total

    if len(_pending_rpc[request_id]["chunks"]) >= chunk_total:
        logger.info("rpc_response_complete", request_id=request_id, house_id=house_id)
        _pending_rpc.pop(request_id, None)
