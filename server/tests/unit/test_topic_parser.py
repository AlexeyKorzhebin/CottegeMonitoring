"""Unit tests for MQTT topic parser."""

from cottage_monitoring.mqtt.topic_parser import MessageType, parse_topic


class TestParseTopic:
    """Tests for parse_topic function with cm/<house_id>/<device_id>/v1/<rest> format."""

    def test_event_topic(self):
        result = parse_topic("cm/house-01/lm-main/v1/events", prefix="")
        assert result is not None
        assert result.house_id == "house-01"
        assert result.device_id == "lm-main"
        assert result.message_type == MessageType.EVENT
        assert result.params == {}

    def test_state_topic(self):
        result = parse_topic("cm/house-01/lm-main/v1/state/ga/1/1/1", prefix="")
        assert result is not None
        assert result.house_id == "house-01"
        assert result.device_id == "lm-main"
        assert result.message_type == MessageType.STATE
        assert result.params == {"ga": "1/1/1"}

    def test_meta_full_topic(self):
        result = parse_topic("cm/house-01/lm-main/v1/meta/objects", prefix="")
        assert result is not None
        assert result.house_id == "house-01"
        assert result.device_id == "lm-main"
        assert result.message_type == MessageType.META_FULL
        assert result.params == {}

    def test_meta_chunk_topic(self):
        result = parse_topic("cm/house-01/lm-main/v1/meta/objects/chunk/2", prefix="")
        assert result is not None
        assert result.house_id == "house-01"
        assert result.device_id == "lm-main"
        assert result.message_type == MessageType.META_CHUNK
        assert result.params == {"chunk_no": 2}

    def test_status_topic(self):
        result = parse_topic("cm/house-01/lm-main/v1/status/online", prefix="")
        assert result is not None
        assert result.house_id == "house-01"
        assert result.device_id == "lm-main"
        assert result.message_type == MessageType.STATUS
        assert result.params == {}

    def test_cmd_ack_topic(self):
        result = parse_topic("cm/house-01/lm-main/v1/cmd/ack/req-123", prefix="")
        assert result is not None
        assert result.house_id == "house-01"
        assert result.device_id == "lm-main"
        assert result.message_type == MessageType.CMD_ACK
        assert result.params == {"request_id": "req-123"}

    def test_rpc_resp_topic(self):
        result = parse_topic("cm/house-01/lm-main/v1/rpc/resp/client-1/req-456", prefix="")
        assert result is not None
        assert result.house_id == "house-01"
        assert result.device_id == "lm-main"
        assert result.message_type == MessageType.RPC_RESP
        assert result.params == {"client_id": "client-1", "request_id": "req-456"}

    def test_with_dev_prefix(self):
        result = parse_topic("dev/cm/house-01/lm-main/v1/events", prefix="dev/")
        assert result is not None
        assert result.house_id == "house-01"
        assert result.device_id == "lm-main"
        assert result.message_type == MessageType.EVENT
        assert result.params == {}

    def test_with_empty_prefix(self):
        result = parse_topic("cm/house-01/lm-main/v1/events", prefix="")
        assert result is not None
        assert result.message_type == MessageType.EVENT

    def test_different_device_id(self):
        result = parse_topic("cm/house-01/lm-floor2/v1/events", prefix="")
        assert result is not None
        assert result.house_id == "house-01"
        assert result.device_id == "lm-floor2"
        assert result.message_type == MessageType.EVENT

    def test_invalid_topic(self):
        result = parse_topic("invalid/topic", prefix="")
        assert result is None

    def test_wrong_prefix(self):
        result = parse_topic("cm/house-01/lm-main/v1/events", prefix="dev/")
        assert result is None

    def test_missing_segments(self):
        result = parse_topic("cm/house-01", prefix="")
        assert result is None

    def test_missing_device_id(self):
        result = parse_topic("cm/house-01/v1/events", prefix="")
        assert result is None

    def test_wrong_namespace(self):
        result = parse_topic("other/house-01/lm-main/v1/events", prefix="")
        assert result is None

    def test_old_lm_namespace_rejected(self):
        result = parse_topic("lm/house-01/v1/events", prefix="")
        assert result is None

    def test_meta_chunk_invalid_number(self):
        result = parse_topic("cm/house-01/lm-main/v1/meta/objects/chunk/abc", prefix="")
        assert result is None
