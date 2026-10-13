"""
protocol.py — TCP framing and JSON envelope protocol.

Every message (request or response) is framed as:
    <4-byte big-endian length><JSON payload>

Request envelope:
    {
        "resource": "fighters",   # entity domain (fighters/tournaments/etc.)
        "action":   "list",       # operation name
        "payload":  {}            # optional operation-specific data (dict)
    }

Response envelope:
    {
        "success": true,
        "data":    <any JSON value>,   # present on success
        "error":   null
    }
    OR
    {
        "success": false,
        "data":    null,
        "error":   "Human-readable error message"
    }
"""

from __future__ import annotations

import json
import socket
import struct
from typing import Any

# ── Constants ──────────────────────────────────────────────────────────────────

HEADER_FORMAT = "!I"          # network byte-order unsigned 32-bit int
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
MAX_MESSAGE_BYTES = 64 * 1024 * 1024   # 64 MiB safety cap


# ── Low-level framing ──────────────────────────────────────────────────────────

def send_message(sock: socket.socket, data: dict[str, Any]) -> None:
    """Serialise *data* to JSON, prefix with a 4-byte length header, and send."""
    payload = json.dumps(data, default=str).encode("utf-8")
    header = struct.pack(HEADER_FORMAT, len(payload))
    sock.sendall(header + payload)


def receive_message(sock: socket.socket) -> dict[str, Any]:
    """Read one framed message from *sock* and return the decoded dict.

    Raises:
        ConnectionError: if the peer closed the connection mid-message.
        ValueError:      if the declared length exceeds MAX_MESSAGE_BYTES.
    """
    raw_header = _recv_exactly(sock, HEADER_SIZE)
    (length,) = struct.unpack(HEADER_FORMAT, raw_header)
    if length > MAX_MESSAGE_BYTES:
        raise ValueError(
            f"Incoming message length {length} exceeds limit {MAX_MESSAGE_BYTES}."
        )
    raw_body = _recv_exactly(sock, length)
    return json.loads(raw_body.decode("utf-8"))


def _recv_exactly(sock: socket.socket, n: int) -> bytes:
    """Read exactly *n* bytes from *sock*, blocking until all arrive."""
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Connection closed by remote peer.")
        buf.extend(chunk)
    return bytes(buf)


# ── Response builders ──────────────────────────────────────────────────────────

def ok(data: Any = None) -> dict[str, Any]:
    """Build a successful response envelope."""
    return {"success": True, "data": data, "error": None}


def error(message: str) -> dict[str, Any]:
    """Build an error response envelope."""
    return {"success": False, "data": None, "error": message}


# ── Request validation ─────────────────────────────────────────────────────────

VALID_RESOURCES = frozenset(
    {
        "fighters",
        "tournaments",
        "categories",
        "matches",
        "registrations",
    }
)


def validate_request(request: dict[str, Any]) -> str | None:
    """Return an error message string if *request* is invalid, else None."""
    if not isinstance(request, dict):
        return "Request must be a JSON object."
    if "resource" not in request:
        return "Missing field: 'resource'."
    if "action" not in request:
        return "Missing field: 'action'."
    if request["resource"] not in VALID_RESOURCES:
        return (
            f"Unknown resource '{request['resource']}'. "
            f"Valid resources: {sorted(VALID_RESOURCES)}."
        )
    return None
