"""Integration tests for RPC request/response handling."""

from __future__ import annotations

import pytest

from cottage_monitoring.services.rpc_service import _pending_rpc, handle_rpc_response

pytestmark = pytest.mark.integration


async def test_rpc_response_single_chunk() -> None:
    """handle_rpc_response chunk 1/1 → request completed, removed from _pending_rpc."""
    house_id = "house-rpc-single"
    client_id = "test-client"
    request_id = "req-single-001"

    _pending_rpc[request_id] = {"chunks": {}, "chunk_total": 1}

    await handle_rpc_response(
        house_id,
        client_id,
        request_id,
        {"chunk_no": 1, "chunk_total": 1, "result": {"meta": "ok"}},
    )

    assert request_id not in _pending_rpc


async def test_rpc_response_multi_chunk() -> None:
    """Send 2 chunks → after chunk 2, request completed."""
    house_id = "house-rpc-multi"
    client_id = "test-client"
    request_id = "req-multi-002"

    _pending_rpc[request_id] = {"chunks": {}, "chunk_total": 2}

    await handle_rpc_response(
        house_id,
        client_id,
        request_id,
        {"chunk_no": 1, "chunk_total": 2, "result": {"objects": [{"id": 1}]}},
    )

    assert request_id in _pending_rpc

    await handle_rpc_response(
        house_id,
        client_id,
        request_id,
        {"chunk_no": 2, "chunk_total": 2, "result": {"objects": [{"id": 2}]}},
    )

    assert request_id not in _pending_rpc
