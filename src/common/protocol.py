"""Wire protocol shared by the TCP client and the TCP server.

Every message (request or response) is framed as::

    <4-byte big-endian unsigned length><UTF-8 JSON payload>

Request envelope::

    {"resource": "fighters", "action": "list", "payload": {}}

Success response::

    {"success": true, "data": <any JSON>, "error": null,
     "error_code": null}

Error response::

    {"success": false, "data": null, "error": "Readable message",
     "error_code": "NOT_FOUND"}

The full specification lives in ``docs/PROTOCOL.md``.
"""

from __future__ import annotations

import json
import socket
import struct
from typing import Any

# -- Constants ---------------------------------------------------------

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9000

HEADER_FORMAT = "!I"  # network byte order, unsigned 32-bit integer
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
MAX_MESSAGE_BYTES = 64 * 1024 * 1024  # 64 MiB safety cap

VALID_RESOURCES = frozenset(
    {
        "fighters",
        "tournaments",
        "categories",
        "matches",
        "registrations",
    }
)


class ErrorCode:
    """Machine-readable error identifiers sent in ``error_code``."""

    BAD_REQUEST = "BAD_REQUEST"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNKNOWN_ACTION = "UNKNOWN_ACTION"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# -- Exceptions --------------------------------------------------------


class MalformedMessageError(ValueError):
    """The frame was fully received but its body is not valid JSON.

    The stream is still correctly aligned, so the connection can keep
    being used after answering with an error response.
    """


class MessageTooLargeError(ValueError):
    """The declared frame length exceeds ``MAX_MESSAGE_BYTES``.

    The body is not read, so the stream is misaligned and the
    connection must be closed.
    """


# -- Low-level framing -------------------------------------------------


def send_message(sock: socket.socket, data: dict[str, Any]) -> None:
    """Serialise *data* to JSON, prefix a length header and send it."""
    payload = json.dumps(data, default=str).encode("utf-8")
    header = struct.pack(HEADER_FORMAT, len(payload))
    sock.sendall(header + payload)


def receive_message(sock: socket.socket) -> Any:
    """Read one framed message from *sock* and return the decoded JSON.

    Raises:
        ConnectionError: the peer closed the connection mid-message.
        MessageTooLargeError: the declared length exceeds the limit.
        MalformedMessageError: the body is not valid UTF-8 JSON.
    """
    raw_header = _recv_exactly(sock, HEADER_SIZE)
    (length,) = struct.unpack(HEADER_FORMAT, raw_header)
    if length > MAX_MESSAGE_BYTES:
        raise MessageTooLargeError(
            f"Incoming message length {length} exceeds limit "
            f"{MAX_MESSAGE_BYTES}."
        )
    raw_body = _recv_exactly(sock, length)
    try:
        return json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MalformedMessageError(f"Malformed JSON body: {exc}") from exc


def _recv_exactly(sock: socket.socket, size: int) -> bytes:
    """Read exactly *size* bytes, blocking until they all arrive."""
    buffer = bytearray()
    while len(buffer) < size:
        chunk = sock.recv(size - len(buffer))
        if not chunk:
            raise ConnectionError("Connection closed by remote peer.")
        buffer.extend(chunk)
    return bytes(buffer)


# -- Response builders -------------------------------------------------


def ok(data: Any = None) -> dict[str, Any]:
    """Build a successful response envelope."""
    return {"success": True, "data": data, "error": None, "error_code": None}


def error(message: str, code: str = ErrorCode.BAD_REQUEST) -> dict[str, Any]:
    """Build an error response envelope."""
    return {
        "success": False,
        "data": None,
        "error": message,
        "error_code": code,
    }


# -- Request validation ------------------------------------------------


def validate_request(request: Any) -> str | None:
    """Return an error message if *request* is invalid, else ``None``.

    Only the structure of the envelope is checked here; the contents of
    ``payload`` are validated by the services.
    """
    if not isinstance(request, dict):
        return "Request must be a JSON object."
    if "resource" not in request:
        return "Missing field: 'resource'."
    if "action" not in request:
        return "Missing field: 'action'."
    resource, action = request["resource"], request["action"]
    if not isinstance(resource, str) or not isinstance(action, str):
        return "Fields 'resource' and 'action' must be strings."
    if resource not in VALID_RESOURCES:
        return (
            f"Unknown resource '{resource}'. "
            f"Valid resources: {sorted(VALID_RESOURCES)}."
        )
    if not isinstance(request.get("payload") or {}, dict):
        return "Field 'payload' must be a JSON object."
    return None
