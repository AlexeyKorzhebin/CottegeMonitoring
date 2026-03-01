"""Unit tests for MQTT topic parser."""

from cottage_monitoring.mqtt.topic_parser import MessageType, parse_topic


class TestParseTopic:
    """Tests for parse_topic function."""

    def test_event_topic(self):
        """EVENT: lm/house-01/v1/events → house_id, EVENT, params={}."""
        result = parse_topic("lm/house-01/v1/events", prefix="")
        assert result is not None
        assert result.house_id == "house-01"
        assert result.message_type == MessageType.EVENT
        assert result.params == {}

    def test_state_topic(self):
        """STATE: lm/house-01/v1/state/ga/1/1/1 → STATE, params={'ga': '1/1/1'}."""
        result = parse_topic("lm/house-01/v1/state/ga/1/1/1", prefix="")
        assert result is not None
        assert result.house_id == "house-01"
        assert result.message_type == MessageType.STATE
        assert result.params == {"ga": "1/1/1"}

    def test_meta_full_topic(self):
        """META_FULL: lm/house-01/v1/meta/objects → META_FULL, params={}."""
        result = parse_topic("lm/house-01/v1/meta/objects", prefix="")
        assert result is not None
        assert result.house_id == "house-01"
        assert result.message_type == MessageType.META_FULL
        assert result.params == {}

    def test_meta_chunk_topic(self):
        """META_CHUNK: lm/house-01/v1/meta/objects/chunk/2 → META_CHUNK, params={'chunk_no': 2}."""
        result = parse_topic("lm/house-01/v1/meta/objects/chunk/2", prefix="")
        assert result is not None
        assert result.house_id == "house-01"
        assert result.message_type == MessageType.META_CHUNK
        assert result.params == {"chunk_no": 2}

    def test_status_topic(self):
        """STATUS: lm/house-01/v1/status/online → STATUS, params={}."""
        result = parse_topic("lm/house-01/v1/status/online", prefix="")
        assert result is not None
        assert result.house_id == "house-01"
        assert result.message_type == MessageType.STATUS
        assert result.params == {}

    def test_cmd_ack_topic(self):
        """CMD_ACK: lm/house-01/v1/cmd/ack/req-123 → CMD_ACK, params={'request_id': 'req-123'}."""
        result = parse_topic("lm/house-01/v1/cmd/ack/req-123", prefix="")
        assert result is not None
        assert result.house_id == "house-01"
        assert result.message_type == MessageType.CMD_ACK
        assert result.params == {"request_id": "req-123"}

    def test_rpc_resp_topic(self):
        """RPC_RESP: rpc/resp/client-1/req-456 → params client_id, request_id."""
        result = parse_topic("lm/house-01/v1/rpc/resp/client-1/req-456", prefix="")
        assert result is not None
        assert result.house_id == "house-01"
        assert result.message_type == MessageType.RPC_RESP
        assert result.params == {"client_id": "client-1", "request_id": "req-456"}

    def test_with_dev_prefix(self):
        """With dev/ prefix: dev/lm/house-01/v1/events → EVENT."""
        result = parse_topic("dev/lm/house-01/v1/events", prefix="dev/")
        assert result is not None
        assert result.house_id == "house-01"
        assert result.message_type == MessageType.EVENT
        assert result.params == {}

    def test_with_empty_prefix(self):
        """With empty prefix: lm/house-01/v1/events → EVENT."""
        result = parse_topic("lm/house-01/v1/events", prefix="")
        assert result is not None
        assert result.message_type == MessageType.EVENT

    def test_invalid_topic(self):
        """Invalid topic: invalid/topic → None."""
        result = parse_topic("invalid/topic", prefix="")
        assert result is None

    def test_wrong_prefix(self):
        """Wrong prefix: dev/ prefix but topic lm/house-01/v1/events (no dev/) → None."""
        result = parse_topic("lm/house-01/v1/events", prefix="dev/")
        assert result is None

    def test_missing_segments(self):
        """Missing segments: lm/house-01 → None."""
        result = parse_topic("lm/house-01", prefix="")
        assert result is None

    def test_wrong_namespace(self):
        """Wrong namespace: other/house-01/v1/events → None."""
        result = parse_topic("other/house-01/v1/events", prefix="")
        assert result is None
