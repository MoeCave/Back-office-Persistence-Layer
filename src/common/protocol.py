"""Wire protocol shared by the TCP client and the TCP server.

Protocolo de red compartido entre el cliente y el servidor TCP.

Estructura de tramas en la red:
1. Tramas en texto plano (exclusivas del handshake M1->M4):
    <4B big-endian '!I' (longitud N)><payload JSON UTF-8 de N bytes>

2. Tramas cifradas de sesión (peticiones y respuestas post-handshake):
    <4B big-endian '!I' (longitud 8 + len(cifrado))>
    <8B big-endian '!Q' uint64 seq>
    <AES-256-GCM ciphertext + 16B tag>

Estructura del sobre de petición (Request envelope)::
    {"resource": "fighters", "action": "list", "payload": {}}

Estructura del sobre de respuesta exitosa (Success response)::
    {"success": true, "data": <any JSON>, "error": null, "error_code": null}

Estructura del sobre de respuesta con error (Error response)::
    {"success": false, "data": null, "error": "...", "error_code": "NOT_FOUND"}

La especificación completa del protocolo se documenta en ``docs/PROTOCOL.md``.
"""

from __future__ import annotations

import asyncio
import json
import socket
import struct
from typing import Any

from src.common.crypto import CipherIntegrityError, SessionCipher

# -- Constantes del protocolo ------------------------------------------

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9000

# Cabecera: 4 bytes big-endian con entero sin signo de 32 bits ('!I')
HEADER_FORMAT = "!I"  # network byte order, unsigned 32-bit integer
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

# Contador de secuencia en tramas cifradas: 8 bytes big-endian uint64 ('!Q')
SEQ_FORMAT = "!Q"  # network byte order, unsigned 64-bit sequence counter
SEQ_SIZE = struct.calcsize(SEQ_FORMAT)

# Límites de seguridad para evitar DoS por tramas sobredimensionadas
MAX_MESSAGE_BYTES = 64 * 1024 * 1024  # 64 MiB safety cap
MAX_HANDSHAKE_BYTES = (
    64 * 1024
)  # 64 KiB cap for unauthenticated handshake frames

# Recursos válidos reconocidos por el servidor
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
    """Códigos de error legibles por máquina enviados en ``error_code``."""

    BAD_REQUEST = "BAD_REQUEST"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNKNOWN_ACTION = "UNKNOWN_ACTION"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    AUTH_FAILED = "AUTH_FAILED"
    INTEGRITY_ERROR = "INTEGRITY_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# -- Excepciones -------------------------------------------------------


class MalformedMessageError(ValueError):
    """El cuerpo recibido no es JSON válido o no respeta UTF-8.

    Dado que la longitud declarada se leyó por completo, el flujo TCP
    permanece alineado y la conexión puede continuar utilizándose.
    """


class MessageTooLargeError(ValueError):
    """La longitud declarada en cabecera supera el límite de seguridad.

    Como el cuerpo no se lee para proteger memoria, el flujo queda
    desalineado y la conexión debe cerrarse de inmediato.
    """


# -- Ayudantes puros de enmarcado (Sans-I/O) ----------------------------


def encode_message(data: dict[str, Any]) -> bytes:
    """Serializa un dict a JSON UTF-8 y antepone su longitud de 4 bytes."""
    payload = json.dumps(data, default=str).encode("utf-8")
    header = struct.pack(HEADER_FORMAT, len(payload))
    return header + payload


def decode_header(
    raw_header: bytes, max_bytes: int = MAX_MESSAGE_BYTES
) -> int:
    """Decodifica los 4 bytes de cabecera y verifica el límite *max_bytes*.

    Lanza:
        MessageTooLargeError: Si la longitud declarada supera el límite.
    """
    (length,) = struct.unpack(HEADER_FORMAT, raw_header)
    if length > max_bytes:
        raise MessageTooLargeError(
            f"Incoming message length {length} exceeds limit {max_bytes}."
        )
    return length


def decode_body(raw_body: bytes) -> Any:
    """Decodifica el cuerpo de la trama JSON UTF-8 en un objeto de Python.

    Lanza:
        MalformedMessageError: Si el payload no es UTF-8 o JSON válido.
    """
    try:
        return json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MalformedMessageError(f"Malformed JSON body: {exc}") from exc


def encode_encrypted_message(
    cipher: SessionCipher, data: dict[str, Any]
) -> bytes:
    """Serializa *data*, cifra con AES-256-GCM y antepone secuencia y longitud.

    Estructura de la trama:
    [4B longitud total][8B secuencia uint64][Cifrado AES-256-GCM + 16B tag]
    """
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
    """Verifica secuencia y tag GCM, descifra *raw_body* y parsea el JSON.

    Lanza:
        CipherIntegrityError: Si falla la autenticación de la trama.
    """
    if len(raw_body) <= SEQ_SIZE:
        raise CipherIntegrityError(
            f"Encrypted frame too short ({len(raw_body)} bytes) for sequence"
            f"header."
        )
    (seq,) = struct.unpack(SEQ_FORMAT, raw_body[:SEQ_SIZE])
    ciphertext = raw_body[SEQ_SIZE:]
    plaintext = cipher.decrypt_frame(seq, ciphertext)
    return decode_body(plaintext)


# -- Adaptadores síncronos sobre sockets bloqueantes -------------------


def send_message(sock: socket.socket, data: dict[str, Any]) -> None:
    """Envía un mensaje en texto plano mediante el socket síncrono."""
    sock.sendall(encode_message(data))


def receive_message(
    sock: socket.socket, max_bytes: int = MAX_MESSAGE_BYTES
) -> Any:
    """Lee un mensaje enmarcado del socket y devuelve el JSON decodificado.

    Lanza:
        ConnectionError: Si el peer cierra la conexión a mitad de trama.
        MessageTooLargeError: Si la longitud declarada excede el límite.
        MalformedMessageError: Si el cuerpo recibido no es JSON válido.
    """
    raw_header = _recv_exactly(sock, HEADER_SIZE)
    length = decode_header(raw_header, max_bytes=max_bytes)
    raw_body = _recv_exactly(sock, length)
    return decode_body(raw_body)


def send_encrypted_message(
    sock: socket.socket, cipher: SessionCipher, data: dict[str, Any]
) -> None:
    """Cifra *data* con AES-256-GCM y envía la trama completa por el socket."""
    sock.sendall(encode_encrypted_message(cipher, data))


def receive_encrypted_message(
    sock: socket.socket, cipher: SessionCipher
) -> Any:
    """Lee y descifra una trama AES-256-GCM recibida del socket bloqueante."""
    raw_header = _recv_exactly(sock, HEADER_SIZE)
    length = decode_header(raw_header)
    raw_body = _recv_exactly(sock, length)
    return decode_encrypted_body(cipher, raw_body)


def _recv_exactly(sock: socket.socket, size: int) -> bytes:
    """Lee exactamente *size* bytes del socket bloqueando hasta completar."""
    buffer = bytearray()
    while len(buffer) < size:
        chunk = sock.recv(size - len(buffer))
        if not chunk:
            raise ConnectionError("Connection closed by remote peer.")
        buffer.extend(chunk)
    return bytes(buffer)


# -- Adaptadores asíncronos sobre flujos de asyncio --------------------


async def write_message(
    writer: asyncio.StreamWriter, data: dict[str, Any]
) -> None:
    """Serializa y escribe un mensaje en texto plano en el flujo asíncrono."""
    writer.write(encode_message(data))
    await writer.drain()


async def read_message(
    reader: asyncio.StreamReader, max_bytes: int = MAX_MESSAGE_BYTES
) -> Any:
    """Lee un mensaje en texto plano del flujo respetando fragmentación TCP."""
    raw_header = await _read_exactly(reader, HEADER_SIZE)
    length = decode_header(raw_header, max_bytes=max_bytes)
    raw_body = await _read_exactly(reader, length)
    return decode_body(raw_body)


async def write_encrypted_message(
    writer: asyncio.StreamWriter, cipher: SessionCipher, data: dict[str, Any]
) -> None:
    """Cifra con AES-256-GCM y escribe la trama en el flujo asíncrono."""
    writer.write(encode_encrypted_message(cipher, data))
    await writer.drain()


async def read_encrypted_message(
    reader: asyncio.StreamReader, cipher: SessionCipher
) -> Any:
    """Lee y descifra una trama AES-256-GCM del flujo asíncrono."""
    raw_header = await _read_exactly(reader, HEADER_SIZE)
    length = decode_header(raw_header)
    raw_body = await _read_exactly(reader, length)
    return decode_encrypted_body(cipher, raw_body)


async def _read_exactly(reader: asyncio.StreamReader, size: int) -> bytes:
    """Lee exactamente *size* bytes traduciendo EOF a ConnectionError."""
    try:
        return await reader.readexactly(size)
    except asyncio.IncompleteReadError as exc:
        raise ConnectionError("Connection closed by remote peer.") from exc


# -- Constructores de sobres de respuesta ------------------------------


def ok(data: Any = None) -> dict[str, Any]:
    """Construye un sobre de respuesta de éxito estándar."""
    return {"success": True, "data": data, "error": None, "error_code": None}


def error(message: str, code: str = ErrorCode.BAD_REQUEST) -> dict[str, Any]:
    """Construye un sobre de respuesta con error tipado."""
    return {
        "success": False,
        "data": None,
        "error": message,
        "error_code": code,
    }


# -- Validación estructural del sobre de petición ---------------------


def validate_request(request: Any) -> str | None:
    """Valida la estructura del sobre de petición recibido.

    Retorna un mensaje de error si es inválida, o ``None`` si es correcta.
    Solo valida el formato superficial del protocolo; el contenido de
    ``payload`` lo validan los servicios.
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
