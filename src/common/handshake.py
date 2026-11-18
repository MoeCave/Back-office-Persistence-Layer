"""Mutual certificate authentication and AES-256-GCM session establishment.

Autenticación mutua con certificados X.509 y sesión AES-256-GCM.
Implementa el intercambio estricto de 4 mensajes (M1 -> M4):
  M1 (C -> S): {"type": "client_hello", "version": ..., "nonce_c": ...}
      El cliente presenta su certificado X.509 y un reto nonce_c.
  M2 (S -> C): {"type": "server_hello", "nonce_s": ..., "signature": ...}
      El servidor valida el certificado de C, responde con cert_S, nonce_s
      y firma RSA-PSS("SERVER_HELLO:" || nonce_c || nonce_s || sha256(cert_C)).
  M3 (C -> S): {"type": "client_proof", "signature": ...}
      El cliente valida cert_S, verifica M2 y demuestra posesión de clave
      firmando ("CLIENT_PROOF:" || nonce_s || nonce_c || sha256(cert_S)).
  M4 (S -> C): {"type": "session_key", "encrypted_key": ...}
      El servidor verifica M3, genera la clave efímera AES-256 y la empaqueta
      con RSA-OAEP vinculando ambos nonces.

Ambos extremos calculan el SHA-256 del transcript completo (M1..M4)
e inicializan su SessionCipher para el tráfico posterior.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import socket
from concurrent.futures import Executor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src.common.crypto import (
    AES_KEY_SIZE,
    NONCE_SIZE,
    Direction,
    HandshakeCryptoError,
    SessionCipher,
    certificate_fingerprint_sha256,
    extract_common_name,
    load_certificate_file,
    load_certificate_pem,
    load_private_key_file,
    sign_pss,
    unwrap_session_key,
    validate_peer_certificate,
    verify_pss,
    wrap_session_key,
)
from src.common.protocol import (
    MAX_HANDSHAKE_BYTES,
    read_message,
    receive_message,
    send_message,
    write_message,
)

DEFAULT_HANDSHAKE_TIMEOUT = 10.0
HANDSHAKE_PROTOCOL_VERSION = "2.0-secure"


@dataclass(frozen=True)
class ServerSecurityConfig:
    """Server PKI credentials and handshake policy."""

    cert: x509.Certificate
    cert_pem: str
    private_key: rsa.RSAPrivateKey
    ca_cert: x509.Certificate
    handshake_timeout: float = DEFAULT_HANDSHAKE_TIMEOUT

    @classmethod
    def from_files(
        cls,
        *,
        cert_path: Path | str,
        key_path: Path | str,
        ca_path: Path | str,
        key_password: bytes | None = None,
        handshake_timeout: float = DEFAULT_HANDSHAKE_TIMEOUT,
    ) -> "ServerSecurityConfig":
        cert_pem = Path(cert_path).read_text(encoding="utf-8")
        cert = load_certificate_pem(cert_pem.encode("utf-8"))
        private_key = load_private_key_file(key_path, password=key_password)
        ca_cert = load_certificate_file(ca_path)
        return cls(
            cert=cert,
            cert_pem=cert_pem,
            private_key=private_key,
            ca_cert=ca_cert,
            handshake_timeout=handshake_timeout,
        )


@dataclass(frozen=True)
class ClientSecurityConfig:
    """Client PKI credentials and server verification policy."""

    cert: x509.Certificate
    cert_pem: str
    private_key: rsa.RSAPrivateKey
    ca_cert: x509.Certificate
    server_hostname: str | None = "localhost"
    handshake_timeout: float = DEFAULT_HANDSHAKE_TIMEOUT

    @classmethod
    def from_files(
        cls,
        *,
        cert_path: Path | str,
        key_path: Path | str,
        ca_path: Path | str,
        server_hostname: str | None = "localhost",
        key_password: bytes | None = None,
        handshake_timeout: float = DEFAULT_HANDSHAKE_TIMEOUT,
    ) -> "ClientSecurityConfig":
        cert_pem = Path(cert_path).read_text(encoding="utf-8")
        cert = load_certificate_pem(cert_pem.encode("utf-8"))
        private_key = load_private_key_file(key_path, password=key_password)
        ca_cert = load_certificate_file(ca_path)
        return cls(
            cert=cert,
            cert_pem=cert_pem,
            private_key=private_key,
            ca_cert=ca_cert,
            server_hostname=server_hostname,
            handshake_timeout=handshake_timeout,
        )


@dataclass
class AuthenticatedSession:
    """Result of a completed mutual handshake."""

    cipher: SessionCipher
    peer_cert: x509.Certificate
    peer_common_name: str
    peer_fingerprint_sha256: str
    transcript_hash: bytes


# ---------------------------------------------------------------------------
# Pure transcript & serialization helpers
# ---------------------------------------------------------------------------


def _canonical_json_bytes(msg: dict[str, Any]) -> bytes:
    return json.dumps(msg, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _compute_transcript_hash(*messages: dict[str, Any]) -> bytes:
    hasher = hashlib.sha256()
    for msg in messages:
        hasher.update(_canonical_json_bytes(msg))
    return hasher.digest()


def _server_hello_signed_bytes(
    nonce_c: bytes, nonce_s: bytes, client_cert_der: bytes
) -> bytes:
    return (
        b"SERVER_HELLO:"
        + nonce_c
        + nonce_s
        + hashlib.sha256(client_cert_der).digest()
    )


def _client_proof_signed_bytes(
    nonce_s: bytes, nonce_c: bytes, server_cert_der: bytes
) -> bytes:
    return (
        b"CLIENT_PROOF:"
        + nonce_s
        + nonce_c
        + hashlib.sha256(server_cert_der).digest()
    )


def _require_handshake_dict(msg: Any, expected_type: str) -> dict[str, Any]:
    if not isinstance(msg, dict):
        raise HandshakeCryptoError("Handshake frame must be a JSON object.")
    if msg.get("success") is False and "error" in msg:
        code = msg.get("error_code") or "AUTH_FAILED"
        raise HandshakeCryptoError(
            f"Server rejected handshake [{code}]: {msg['error']}"
        )
    actual_type = msg.get("type")
    if actual_type != expected_type:
        raise HandshakeCryptoError(
            f"Unexpected handshake message type: got {actual_type!r}, "
            f"expected {expected_type!r}"
        )
    return msg


def _decode_hex(value: Any, expected_len: int, field_name: str) -> bytes:
    if not isinstance(value, str):
        raise HandshakeCryptoError(
            f"Handshake field '{field_name}' must be a hex string."
        )
    try:
        raw = bytes.fromhex(value)
    except ValueError as exc:
        raise HandshakeCryptoError(f"Invalid hex in '{field_name}'.") from exc
    if len(raw) != expected_len:
        raise HandshakeCryptoError(
            f"Field '{field_name}' must be {expected_len} bytes, got "
            f"{len(raw)}."
        )
    return raw


def _decode_b64(value: Any, field_name: str) -> bytes:
    if not isinstance(value, str):
        raise HandshakeCryptoError(
            f"Handshake field '{field_name}' must be base64."
        )
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except Exception as exc:
        raise HandshakeCryptoError(
            f"Invalid base64 in '{field_name}'."
        ) from exc


# ---------------------------------------------------------------------------
# CPU-bound cryptographic step helpers (safe to offload to ThreadPoolExecutor)
# ---------------------------------------------------------------------------


def _server_process_m1_and_build_m2(
    config: ServerSecurityConfig,
    m1_raw: Any,
) -> tuple[
    dict[str, Any],
    bytes,
    x509.Certificate,
    rsa.RSAPublicKey,
    bytes,
    dict[str, Any],
]:
    m1 = _require_handshake_dict(m1_raw, "client_hello")
    cert_pem = m1.get("cert_pem")
    if not isinstance(cert_pem, str) or not cert_pem.strip():
        raise HandshakeCryptoError("Missing 'cert_pem' in client_hello.")
    nonce_c = _decode_hex(m1.get("nonce_c"), NONCE_SIZE, "nonce_c")

    client_cert = load_certificate_pem(cert_pem.encode("utf-8"))
    client_pub = validate_peer_certificate(
        client_cert,
        config.ca_cert,
        expect_server=False,
    )

    nonce_s = os.urandom(NONCE_SIZE)
    client_cert_der = client_cert.public_bytes(serialization.Encoding.DER)
    sig = sign_pss(
        config.private_key,
        _server_hello_signed_bytes(nonce_c, nonce_s, client_cert_der),
    )
    m2 = {
        "type": "server_hello",
        "version": HANDSHAKE_PROTOCOL_VERSION,
        "cert_pem": config.cert_pem,
        "nonce_s": nonce_s.hex(),
        "signature": base64.b64encode(sig).decode("ascii"),
    }
    return m1, nonce_c, client_cert, client_pub, nonce_s, m2


def _server_process_m3_and_build_m4(
    config: ServerSecurityConfig,
    m1: dict[str, Any],
    m2: dict[str, Any],
    m3_raw: Any,
    client_cert: x509.Certificate,
    client_pub: rsa.RSAPublicKey,
    nonce_c: bytes,
    nonce_s: bytes,
) -> tuple[AuthenticatedSession, dict[str, Any]]:
    m3 = _require_handshake_dict(m3_raw, "client_proof")
    sig = _decode_b64(m3.get("signature"), "signature")

    server_cert_der = config.cert.public_bytes(serialization.Encoding.DER)
    verify_pss(
        client_pub,
        sig,
        _client_proof_signed_bytes(nonce_s, nonce_c, server_cert_der),
    )

    session_key = os.urandom(AES_KEY_SIZE)
    encrypted_key = wrap_session_key(client_pub, session_key, nonce_c, nonce_s)
    m4 = {
        "type": "session_key",
        "encrypted_key": base64.b64encode(encrypted_key).decode("ascii"),
    }

    transcript_hash = _compute_transcript_hash(m1, m2, m3, m4)
    cipher = SessionCipher(
        session_key=session_key,
        send_direction=Direction.SERVER_TO_CLIENT,
        recv_direction=Direction.CLIENT_TO_SERVER,
        transcript_hash=transcript_hash,
    )
    session = AuthenticatedSession(
        cipher=cipher,
        peer_cert=client_cert,
        peer_common_name=extract_common_name(client_cert),
        peer_fingerprint_sha256=certificate_fingerprint_sha256(client_cert),
        transcript_hash=transcript_hash,
    )
    return session, m4


def _client_build_m1(
    config: ClientSecurityConfig,
) -> tuple[bytes, dict[str, Any]]:
    nonce_c = os.urandom(NONCE_SIZE)
    m1 = {
        "type": "client_hello",
        "version": HANDSHAKE_PROTOCOL_VERSION,
        "cert_pem": config.cert_pem,
        "nonce_c": nonce_c.hex(),
    }
    return nonce_c, m1


def _client_process_m2_and_build_m3(
    config: ClientSecurityConfig,
    nonce_c: bytes,
    m2_raw: Any,
) -> tuple[dict[str, Any], x509.Certificate, bytes, dict[str, Any]]:
    m2 = _require_handshake_dict(m2_raw, "server_hello")
    cert_pem = m2.get("cert_pem")
    if not isinstance(cert_pem, str) or not cert_pem.strip():
        raise HandshakeCryptoError("Missing 'cert_pem' in server_hello.")
    nonce_s = _decode_hex(m2.get("nonce_s"), NONCE_SIZE, "nonce_s")
    sig = _decode_b64(m2.get("signature"), "signature")

    server_cert = load_certificate_pem(cert_pem.encode("utf-8"))
    server_pub = validate_peer_certificate(
        server_cert,
        config.ca_cert,
        expect_server=True,
        expected_hostname=config.server_hostname,
    )
    client_cert_der = config.cert.public_bytes(serialization.Encoding.DER)
    verify_pss(
        server_pub,
        sig,
        _server_hello_signed_bytes(nonce_c, nonce_s, client_cert_der),
    )

    server_cert_der = server_cert.public_bytes(serialization.Encoding.DER)
    client_sig = sign_pss(
        config.private_key,
        _client_proof_signed_bytes(nonce_s, nonce_c, server_cert_der),
    )
    m3 = {
        "type": "client_proof",
        "signature": base64.b64encode(client_sig).decode("ascii"),
    }
    return m2, server_cert, nonce_s, m3


def _client_process_m4(
    config: ClientSecurityConfig,
    m1: dict[str, Any],
    m2: dict[str, Any],
    m3: dict[str, Any],
    m4_raw: Any,
    server_cert: x509.Certificate,
    nonce_c: bytes,
    nonce_s: bytes,
) -> AuthenticatedSession:
    m4 = _require_handshake_dict(m4_raw, "session_key")
    encrypted_key = _decode_b64(m4.get("encrypted_key"), "encrypted_key")
    session_key = unwrap_session_key(
        config.private_key,
        encrypted_key,
        expected_nonce_c=nonce_c,
        expected_nonce_s=nonce_s,
    )
    transcript_hash = _compute_transcript_hash(m1, m2, m3, m4)
    cipher = SessionCipher(
        session_key=session_key,
        send_direction=Direction.CLIENT_TO_SERVER,
        recv_direction=Direction.SERVER_TO_CLIENT,
        transcript_hash=transcript_hash,
    )
    return AuthenticatedSession(
        cipher=cipher,
        peer_cert=server_cert,
        peer_common_name=extract_common_name(server_cert),
        peer_fingerprint_sha256=certificate_fingerprint_sha256(server_cert),
        transcript_hash=transcript_hash,
    )


# ---------------------------------------------------------------------------
# Asyncio Server Handshake
# ---------------------------------------------------------------------------


async def perform_server_handshake_async(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    config: ServerSecurityConfig,
    executor: Executor | None = None,
) -> AuthenticatedSession:
    """Execute the server side of the 4-step mutual authentication
    handshake."""

    async def _run() -> AuthenticatedSession:
        loop = asyncio.get_running_loop()

        # M1: Receive ClientHello
        m1_raw = await read_message(reader, max_bytes=MAX_HANDSHAKE_BYTES)
        (
            m1,
            nonce_c,
            client_cert,
            client_pub,
            nonce_s,
            m2,
        ) = await loop.run_in_executor(
            executor,
            _server_process_m1_and_build_m2,
            config,
            m1_raw,
        )

        # M2: Send ServerHello
        await write_message(writer, m2)

        # M3: Receive ClientProof
        m3_raw = await read_message(reader, max_bytes=MAX_HANDSHAKE_BYTES)
        session, m4 = await loop.run_in_executor(
            executor,
            _server_process_m3_and_build_m4,
            config,
            m1,
            m2,
            m3_raw,
            client_cert,
            client_pub,
            nonce_c,
            nonce_s,
        )

        # M4: Send RSA-OAEP SessionKeyMessage
        await write_message(writer, m4)
        return session

    return await asyncio.wait_for(_run(), timeout=config.handshake_timeout)


# ---------------------------------------------------------------------------
# Blocking Socket Client Handshake
# ---------------------------------------------------------------------------


def perform_client_handshake_sync(
    sock: socket.socket,
    config: ClientSecurityConfig,
) -> AuthenticatedSession:
    """Execute the client side of the 4-step mutual handshake on a blocking
    socket."""
    prev_timeout = sock.gettimeout()
    sock.settimeout(config.handshake_timeout)
    try:
        nonce_c, m1 = _client_build_m1(config)
        send_message(sock, m1)

        m2_raw = receive_message(sock, max_bytes=MAX_HANDSHAKE_BYTES)
        m2, server_cert, nonce_s, m3 = _client_process_m2_and_build_m3(
            config, nonce_c, m2_raw
        )

        send_message(sock, m3)

        m4_raw = receive_message(sock, max_bytes=MAX_HANDSHAKE_BYTES)
        return _client_process_m4(
            config,
            m1,
            m2,
            m3,
            m4_raw,
            server_cert,
            nonce_c,
            nonce_s,
        )
    finally:
        sock.settimeout(prev_timeout)


# ---------------------------------------------------------------------------
# Asyncio Client Handshake
# ---------------------------------------------------------------------------


async def perform_client_handshake_async(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    config: ClientSecurityConfig,
    executor: Executor | None = None,
) -> AuthenticatedSession:
    """Execute the client side of the 4-step mutual handshake over asyncio
    streams."""

    async def _run() -> AuthenticatedSession:
        loop = asyncio.get_running_loop()

        nonce_c, m1 = _client_build_m1(config)
        await write_message(writer, m1)

        m2_raw = await read_message(reader, max_bytes=MAX_HANDSHAKE_BYTES)
        m2, server_cert, nonce_s, m3 = await loop.run_in_executor(
            executor,
            _client_process_m2_and_build_m3,
            config,
            nonce_c,
            m2_raw,
        )

        await write_message(writer, m3)

        m4_raw = await read_message(reader, max_bytes=MAX_HANDSHAKE_BYTES)
        return await loop.run_in_executor(
            executor,
            _client_process_m4,
            config,
            m1,
            m2,
            m3,
            m4_raw,
            server_cert,
            nonce_c,
            nonce_s,
        )

    return await asyncio.wait_for(_run(), timeout=config.handshake_timeout)
