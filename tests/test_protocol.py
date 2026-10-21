"""
test_protocol.py — unit tests for src/server/protocol.py.

Covers:
  - send_message / receive_message round-trip (framing + JSON)
  - ok() and error() response builders
  - validate_request() — valid and invalid inputs
  - ConnectionError when the socket closes mid-read
"""

from __future__ import annotations

import json
import socket
import struct
from typing import Any

import pytest

from src.common.protocol import (
    HEADER_FORMAT,
    MAX_MESSAGE_BYTES,
    ErrorCode,
    MalformedMessageError,
    MessageTooLargeError,
    error,
    ok,
    receive_message,
    send_message,
    validate_request,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_frame(data: dict[str, Any]) -> bytes:
    """Build a length-prefixed JSON frame without using send_message."""
    payload = json.dumps(data).encode("utf-8")
    header = struct.pack(HEADER_FORMAT, len(payload))
    return header + payload


def _loopback_pair():
    """Return a pair of connected blocking sockets."""
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.bind(("127.0.0.1", 0))
    server_sock.listen(1)
    port = server_sock.getsockname()[1]

    client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_sock.connect(("127.0.0.1", port))
    conn, _ = server_sock.accept()
    server_sock.close()
    return client_sock, conn


# ── send_message / receive_message ───────────────────────────────────────────


class TestFraming:
    """Round-trip framing tests using a real loopback socket pair."""

    def test_simple_dict(self):
        sender, receiver = _loopback_pair()
        payload = {"hello": "world", "num": 42}
        send_message(sender, payload)
        result = receive_message(receiver)
        sender.close()
        receiver.close()
        assert result == payload

    def test_nested_payload(self):
        sender, receiver = _loopback_pair()
        payload = {
            "resource": "fighters",
            "action": "create",
            "payload": {"first_name": "Ana", "last_name": "García"},
        }
        send_message(sender, payload)
        result = receive_message(receiver)
        sender.close()
        receiver.close()
        assert result["payload"]["first_name"] == "Ana"

    def test_empty_payload(self):
        sender, receiver = _loopback_pair()
        send_message(sender, {})
        result = receive_message(receiver)
        sender.close()
        receiver.close()
        assert result == {}

    def test_multiple_sequential_messages(self):
        sender, receiver = _loopback_pair()
        messages = [{"idx": i} for i in range(5)]
        for msg in messages:
            send_message(sender, msg)
        received = [receive_message(receiver) for _ in messages]
        sender.close()
        receiver.close()
        assert received == messages

    def test_connection_closed_raises_connection_error(self):
        """receive_message must raise ConnectionError when the peer closes."""
        sender, receiver = _loopback_pair()
        sender.close()  # close without sending anything
        with pytest.raises(ConnectionError):
            receive_message(receiver)
        receiver.close()

    def test_oversized_message_raises_value_error(self):
        """A declared length > MAX_MESSAGE_BYTES must raise ValueError."""
        sender, receiver = _loopback_pair()
        # Send a header claiming MAX + 1 bytes
        bad_header = struct.pack(HEADER_FORMAT, MAX_MESSAGE_BYTES + 1)
        sender.sendall(bad_header)
        with pytest.raises(ValueError, match="exceeds limit"):
            receive_message(receiver)
        sender.close()
        receiver.close()

    def test_non_serialisable_values_are_stringified(self):
        """send_message uses default=str, so non-JSON types are coerced."""
        from datetime import datetime

        sender, receiver = _loopback_pair()
        now = datetime(2026, 1, 1, 12, 0)
        send_message(sender, {"ts": now})
        result = receive_message(receiver)
        sender.close()
        receiver.close()
        assert "2026" in result["ts"]


# ── Response builders ────────────────────────────────────────────────────────


class TestResponseBuilders:
    def test_ok_with_data(self):
        resp = ok({"fighters": []})
        assert resp["success"] is True
        assert resp["data"] == {"fighters": []}
        assert resp["error"] is None

    def test_ok_no_data(self):
        resp = ok()
        assert resp["success"] is True
        assert resp["data"] is None

    def test_error_message(self):
        resp = error("Something went wrong")
        assert resp["success"] is False
        assert resp["data"] is None
        assert resp["error"] == "Something went wrong"

    def test_error_empty_string(self):
        resp = error("")
        assert resp["success"] is False
        assert resp["error"] == ""


# ── validate_request ─────────────────────────────────────────────────────────


class TestValidateRequest:
    def test_valid_fighters_list(self):
        req = {"resource": "fighters", "action": "list", "payload": {}}
        assert validate_request(req) is None

    def test_valid_all_resources(self):
        for resource in (
            "fighters",
            "tournaments",
            "categories",
            "matches",
            "registrations",
        ):
            req = {"resource": resource, "action": "list"}
            assert validate_request(req) is None

    def test_missing_resource_field(self):
        msg = validate_request({"action": "list"})
        assert msg is not None
        assert "resource" in msg

    def test_missing_action_field(self):
        msg = validate_request({"resource": "fighters"})
        assert msg is not None
        assert "action" in msg

    def test_unknown_resource(self):
        msg = validate_request({"resource": "unknown", "action": "list"})
        assert msg is not None
        assert "unknown" in msg.lower() or "Unknown" in msg

    def test_not_a_dict(self):
        msg = validate_request("not a dict")  # type: ignore[arg-type]
        assert msg is not None

    def test_none_input(self):
        msg = validate_request(None)  # type: ignore[arg-type]
        assert msg is not None


# ── Added in v2.0.0: error codes, malformed bodies, stricter validation ──────


class TestErrorEnvelope:
    def test_error_has_code(self):
        resp = error("nope", ErrorCode.NOT_FOUND)
        assert resp["error_code"] == "NOT_FOUND"

    def test_error_default_code_is_bad_request(self):
        assert error("x")["error_code"] == "BAD_REQUEST"

    def test_ok_has_null_error_code(self):
        assert ok()["error_code"] is None


class TestMalformedBodies:
    def _send_raw(self, body: bytes):
        sender, receiver = _loopback_pair()
        sender.sendall(struct.pack(HEADER_FORMAT, len(body)) + body)
        try:
            return receiver
        finally:
            sender.close()

    def test_invalid_json_raises_malformed(self):
        receiver = self._send_raw(b"{oops")
        with pytest.raises(MalformedMessageError):
            receive_message(receiver)
        receiver.close()

    def test_invalid_utf8_raises_malformed(self):
        receiver = self._send_raw(b"\xff\xfe")
        with pytest.raises(MalformedMessageError):
            receive_message(receiver)
        receiver.close()

    def test_stream_stays_aligned_after_malformed_body(self):
        sender, receiver = _loopback_pair()
        bad = b"nope"
        sender.sendall(struct.pack(HEADER_FORMAT, len(bad)) + bad)
        send_message(sender, {"ok": 1})
        with pytest.raises(MalformedMessageError):
            receive_message(receiver)
        assert receive_message(receiver) == {"ok": 1}
        sender.close()
        receiver.close()

    def test_too_large_is_value_error_subclass(self):
        assert issubclass(MessageTooLargeError, ValueError)
        assert issubclass(MalformedMessageError, ValueError)


class TestStricterValidation:
    @pytest.mark.parametrize(
        "request_",
        [
            {"resource": ["x"], "action": "list"},
            {"resource": {}, "action": "list"},
            {"resource": None, "action": "list"},
            {"resource": "fighters", "action": 1},
            {"resource": "fighters", "action": None},
            {"resource": "fighters", "action": "list", "payload": "s"},
            {"resource": "fighters", "action": "list", "payload": [1]},
        ],
    )
    def test_rejects_wrong_types(self, request_):
        assert validate_request(request_) is not None

    def test_null_payload_is_accepted(self):
        request = {"resource": "fighters", "action": "list", "payload": None}
        assert validate_request(request) is None
