"""Wire protocol shared by the TCP client and the TCP server.

Every plain / handshake message is framed as::

    <4-byte big-endian unsigned length><UTF-8 JSON payload>

Every post-handshake encrypted message is framed as::

    <4-byte big-endian unsigned length><8-byte uint64 seq><AES-256-GCM
    ciphertext + 16B tag>

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

import asyncio
import json
import socket
import struct
from typing import Any

from src.common.crypto import CipherIntegrityError, SessionCipher

# -- Constants ---------------------------------------------------------

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9000

HEADER_FORMAT = "!I"  # network byte order, unsigned 32-bit integer
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
SEQ_FORMAT = "!Q"  # network byte order, unsigned 64-bit sequence counter
SEQ_SIZE = struct.calcsize(SEQ_FORMAT)
MAX_MESSAGE_BYTES = 64 * 1024 * 1024  # 64 MiB safety cap
MAX_HANDSHAKE_BYTES = (
    64 * 1024
)  # 64 KiB cap for unauthenticated handshake frames

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
    AUTH_FAILED = "AUTH_FAILED"
    INTEGRITY_ERROR = "INTEGRITY_ERROR"
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


# -- Pure framing helpers (Sans-I/O) -----------------------------------


def encode_message(data: dict[str, Any]) -> bytes:
    """Serialise *data* to UTF-8 JSON and prepend its 4-byte length."""
    payload = json.dumps(data, default=str).encode("utf-8")
    header = struct.pack(HEADER_FORMAT, len(payload))
    return header + payload


def decode_header(
    raw_header: bytes, max_bytes: int = MAX_MESSAGE_BYTES
) -> int:
    """Unpack the 4-byte frame header and enforce *max_bytes*.

    Raises:
        MessageTooLargeError: the declared length exceeds the safety cap.
    """
    (length,) = struct.unpack(HEADER_FORMAT, raw_header)
    if length > max_bytes:
        raise MessageTooLargeError(
            f"Incoming message length {length} exceeds limit {max_bytes}."
        )
    return length


def decode_body(raw_body: bytes) -> Any:
    """Decode a UTF-8 JSON frame body into a Python object.

    Raises:
        MalformedMessageError: the payload is not valid UTF-8 JSON.
    """
    try:
        return json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MalformedMessageError(f"Malformed JSON body: {exc}") from exc


def encode_encrypted_message(
    cipher: SessionCipher, data: dict[str, Any]
) -> bytes:
    """Serialise *data* to JSON, encrypt with AES-256-GCM, and frame with
    seq."""
    plaintext = json.dumps(data, default=str).encode("utf-8")
    seq, ciphertext = cipher.encrypt_frame(plaintext)
    body = struct.pack(SEQ_FORMAT, seq) + ciphertext
    if len(body) > MAX_MESSAGE_BYTES:
        raise MessageTooLargeError(
            f"Encrypted message length {len(body)} exceeds limit "
            f"{MAX_MESSAGE_BYTES}."
        )
    header = struct.pack(HEADER_FORMAT, len(body))
    return header + body


def decode_encrypted_body(cipher: SessionCipher, raw_body: bytes) -> Any:
    """Verify sequence + GCM tag, decrypt *raw_body*, and parse UTF-8 JSON."""
    if len(raw_body) <= SEQ_SIZE:
        raise CipherIntegrityError(
            f"Encrypted frame too short ({len(raw_body)} bytes) for sequence"
            f"header."
        )
    (seq,) = struct.unpack(SEQ_FORMAT, raw_body[:SEQ_SIZE])
    ciphertext = raw_body[SEQ_SIZE:]
    plaintext = cipher.decrypt_frame(seq, ciphertext)
    return decode_body(plaintext)


# -- Synchronous socket framing ----------------------------------------


def send_message(sock: socket.socket, data: dict[str, Any]) -> None:
    """Serialise *data* to JSON, prefix a length header and send it."""
    sock.sendall(encode_message(data))


def receive_message(
    sock: socket.socket, max_bytes: int = MAX_MESSAGE_BYTES
) -> Any:
    """Read one framed message from *sock* and return the decoded JSON.

    Raises:
        ConnectionError: the peer closed the connection mid-message.
        MessageTooLargeError: the declared length exceeds the limit.
        MalformedMessageError: the body is not valid UTF-8 JSON.
    """
    raw_header = _recv_exactly(sock, HEADER_SIZE)
    length = decode_header(raw_header, max_bytes=max_bytes)
    raw_body = _recv_exactly(sock, length)
    return decode_body(raw_body)


def send_encrypted_message(
    sock: socket.socket, cipher: SessionCipher, data: dict[str, Any]
) -> None:
    """Encrypt *data* with AES-256-GCM and send one framed message to
    *sock*."""
    sock.sendall(encode_encrypted_message(cipher, data))


def receive_encrypted_message(
    sock: socket.socket, cipher: SessionCipher
) -> Any:
    """Read and decrypt one AES-256-GCM framed message from *sock*."""
    raw_header = _recv_exactly(sock, HEADER_SIZE)
    length = decode_header(raw_header)
    raw_body = _recv_exactly(sock, length)
    return decode_encrypted_body(cipher, raw_body)


def _recv_exactly(sock: socket.socket, size: int) -> bytes:
    """Read exactly *size* bytes, blocking until they all arrive."""
    buffer = bytearray()
    while len(buffer) < size:
        chunk = sock.recv(size - len(buffer))
        if not chunk:
            raise ConnectionError("Connection closed by remote peer.")
        buffer.extend(chunk)
    return bytes(buffer)


# -- Asynchronous stream framing ---------------------------------------


async def write_message(
    writer: asyncio.StreamWriter, data: dict[str, Any]
) -> None:
    """Serialise *data* and flush the framed message to *writer*."""
    writer.write(encode_message(data))
    await writer.drain()


async def read_message(
    reader: asyncio.StreamReader, max_bytes: int = MAX_MESSAGE_BYTES
) -> Any:
    """Read one framed message from *reader* and return the decoded JSON.

    Raises:
        ConnectionError: the peer closed the stream before frame end.
        MessageTooLargeError: the declared length exceeds the limit.
        MalformedMessageError: the body is not valid UTF-8 JSON.
    """
    raw_header = await _read_exactly(reader, HEADER_SIZE)
    length = decode_header(raw_header, max_bytes=max_bytes)
    raw_body = await _read_exactly(reader, length)
    return decode_body(raw_body)


async def write_encrypted_message(
    writer: asyncio.StreamWriter, cipher: SessionCipher, data: dict[str, Any]
) -> None:
    """Encrypt *data* with AES-256-GCM and flush the framed message to
    *writer*."""
    writer.write(encode_encrypted_message(cipher, data))
    await writer.drain()


async def read_encrypted_message(
    reader: asyncio.StreamReader, cipher: SessionCipher
) -> Any:
    """Read and decrypt one AES-256-GCM framed message from *reader*."""
    raw_header = await _read_exactly(reader, HEADER_SIZE)
    length = decode_header(raw_header)
    raw_body = await _read_exactly(reader, length)
    return decode_encrypted_body(cipher, raw_body)


async def _read_exactly(reader: asyncio.StreamReader, size: int) -> bytes:
    """Read exactly *size* bytes from *reader*, translating EOF errors."""
    try:
        return await reader.readexactly(size)
    except asyncio.IncompleteReadError as exc:
        raise ConnectionError("Connection closed by remote peer.") from exc


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
