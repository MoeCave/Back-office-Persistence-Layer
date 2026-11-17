"""Comprehensive unit and end-to-end TCP tests for mutual PKI +
AES-256-GCM."""

from __future__ import annotations

import asyncio
import os
import socket
import struct
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.domain.models  # noqa: F401 - register ORM tables on Base.metadata
from src.client.async_gateway import AsyncServerGateway
from src.client.gateway import (
    ConnectionFailedError,
    ServerError,
    ServerGateway,
)
from src.common.crypto import (
    CertificateValidationError,
    CipherIntegrityError,
    Direction,
    SessionCipher,
    HandshakeCryptoError,
    load_certificate_file,
    load_private_key_file,
    sign_pss,
    unwrap_session_key,
    validate_peer_certificate,
    verify_pss,
    wrap_session_key,
)
from src.common.handshake import ClientSecurityConfig, ServerSecurityConfig
from src.common.protocol import (
    ErrorCode,
    HEADER_SIZE,
    receive_message,
    send_message,
)
from src.domain.db import Base
from src.server.app import run_server

CERTS_DIR = Path("certs")
CA_PATH = CERTS_DIR / "ca" / "ca.pem"
SRV_CERT_PATH = CERTS_DIR / "server" / "server.pem"
SRV_KEY_PATH = CERTS_DIR / "server" / "server.key"
CLI1_CERT_PATH = CERTS_DIR / "client1" / "client1.pem"
CLI1_KEY_PATH = CERTS_DIR / "client1" / "client1.key"
CLI2_CERT_PATH = CERTS_DIR / "client2" / "client2.pem"
CLI2_KEY_PATH = CERTS_DIR / "client2" / "client2.key"
ROGUE_CERT_PATH = CERTS_DIR / "test_invalid" / "rogue_client.pem"
ROGUE_KEY_PATH = CERTS_DIR / "test_invalid" / "rogue_client.key"
EXPIRED_CERT_PATH = CERTS_DIR / "test_invalid" / "expired_client.pem"
EXPIRED_KEY_PATH = CERTS_DIR / "test_invalid" / "expired_client.key"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def server_security() -> ServerSecurityConfig:
    return ServerSecurityConfig.from_files(
        cert_path=SRV_CERT_PATH,
        key_path=SRV_KEY_PATH,
        ca_path=CA_PATH,
    )


@pytest.fixture(scope="module")
def client1_security() -> ClientSecurityConfig:
    return ClientSecurityConfig.from_files(
        cert_path=CLI1_CERT_PATH,
        key_path=CLI1_KEY_PATH,
        ca_path=CA_PATH,
        server_hostname="localhost",
    )


@pytest.fixture(scope="module")
def client2_security() -> ClientSecurityConfig:
    return ClientSecurityConfig.from_files(
        cert_path=CLI2_CERT_PATH,
        key_path=CLI2_KEY_PATH,
        ca_path=CA_PATH,
        server_hostname="localhost",
    )


@pytest.fixture
def db_session_factory(tmp_path):
    db_file = tmp_path / "security_test.db"
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


@pytest.fixture
async def secure_server(db_session_factory, server_security):
    stop_event = asyncio.Event()
    started: asyncio.Future[tuple[str, int]] = asyncio.Future()
    task = asyncio.create_task(
        run_server(
            host="127.0.0.1",
            port=0,
            session_factory=db_session_factory,
            stop_event=stop_event,
            on_started=lambda h, p: started.set_result((h, p)),
            security=server_security,
        )
    )
    host, port = await started
    try:
        yield host, port
    finally:
        stop_event.set()
        await task


# ---------------------------------------------------------------------------
# 1. X.509 Certificate Validation Unit Tests
# ---------------------------------------------------------------------------


def test_x509_valid_server_and_client_certs():
    ca = load_certificate_file(CA_PATH)
    srv = load_certificate_file(SRV_CERT_PATH)
    cli1 = load_certificate_file(CLI1_CERT_PATH)
    cli2 = load_certificate_file(CLI2_CERT_PATH)

    srv_pub = validate_peer_certificate(
        srv, ca, expect_server=True, expected_hostname="localhost"
    )
    srv_pub_ip = validate_peer_certificate(
        srv, ca, expect_server=True, expected_hostname="127.0.0.1"
    )
    cli1_pub = validate_peer_certificate(cli1, ca, expect_server=False)
    cli2_pub = validate_peer_certificate(cli2, ca, expect_server=False)

    assert isinstance(srv_pub, rsa.RSAPublicKey)
    assert isinstance(srv_pub_ip, rsa.RSAPublicKey)
    assert isinstance(cli1_pub, rsa.RSAPublicKey)
    assert isinstance(cli2_pub, rsa.RSAPublicKey)


def test_x509_rejects_untrusted_rogue_ca():
    ca = load_certificate_file(CA_PATH)
    rogue = load_certificate_file(ROGUE_CERT_PATH)

    with pytest.raises(
        CertificateValidationError, match="does not match trusted CA"
    ):
        validate_peer_certificate(rogue, ca, expect_server=False)


def test_x509_rejects_expired_certificate():
    ca = load_certificate_file(CA_PATH)
    expired = load_certificate_file(EXPIRED_CERT_PATH)

    with pytest.raises(CertificateValidationError, match="expired"):
        validate_peer_certificate(expired, ca, expect_server=False)


def test_x509_rejects_role_confusion():
    ca = load_certificate_file(CA_PATH)
    srv = load_certificate_file(SRV_CERT_PATH)
    cli1 = load_certificate_file(CLI1_CERT_PATH)

    with pytest.raises(CertificateValidationError, match="serverAuth"):
        validate_peer_certificate(cli1, ca, expect_server=True)

    with pytest.raises(CertificateValidationError, match="clientAuth"):
        validate_peer_certificate(srv, ca, expect_server=False)


def test_x509_rejects_wrong_server_hostname():
    ca = load_certificate_file(CA_PATH)
    srv = load_certificate_file(SRV_CERT_PATH)

    with pytest.raises(
        CertificateValidationError, match="not present in certificate SAN"
    ):
        validate_peer_certificate(
            srv,
            ca,
            expect_server=True,
            expected_hostname="attacker.example.com",
        )


def test_x509_rejects_tampered_certificate_signature():
    ca = load_certificate_file(CA_PATH)
    cli1 = load_certificate_file(CLI1_CERT_PATH)
    der = bytearray(cli1.public_bytes(serialization.Encoding.DER))
    der[-10] ^= 0xFF
    tampered = x509.load_der_x509_certificate(bytes(der))

    with pytest.raises(
        CertificateValidationError,
        match="signature verification against CA failed",
    ):
        validate_peer_certificate(tampered, ca, expect_server=False)


# ---------------------------------------------------------------------------
# 2. RSA-PSS, RSA-OAEP, and AES-256-GCM SessionCipher Unit Tests
# ---------------------------------------------------------------------------


def test_rsa_pss_sign_and_verify_detects_tampering():
    srv_key = load_private_key_file(SRV_KEY_PATH)
    srv_pub = load_certificate_file(SRV_CERT_PATH).public_key()
    assert isinstance(srv_pub, rsa.RSAPublicKey)

    payload = b"SERVER_HELLO:transcript-binding-test"
    sig = sign_pss(srv_key, payload)
    verify_pss(srv_pub, sig, payload)

    with pytest.raises(HandshakeCryptoError):
        verify_pss(srv_pub, sig, payload + b"-modified")

    bad_sig = bytes([sig[0] ^ 0x01]) + sig[1:]
    with pytest.raises(HandshakeCryptoError):
        verify_pss(srv_pub, bad_sig, payload)


def test_rsa_oaep_session_key_wrap_binds_nonces():
    cli1_pub = load_certificate_file(CLI1_CERT_PATH).public_key()
    cli1_key = load_private_key_file(CLI1_KEY_PATH)
    cli2_key = load_private_key_file(CLI2_KEY_PATH)
    assert isinstance(cli1_pub, rsa.RSAPublicKey)

    nc, ns = os.urandom(16), os.urandom(16)
    aes_key = os.urandom(32)
    wrapped = wrap_session_key(cli1_pub, aes_key, nc, ns)

    assert unwrap_session_key(cli1_key, wrapped, nc, ns) == aes_key

    # Wrong private key must fail
    with pytest.raises(HandshakeCryptoError):
        unwrap_session_key(cli2_key, wrapped, nc, ns)

    # Mismatched nonces must fail
    with pytest.raises(HandshakeCryptoError, match="nonces do not match"):
        unwrap_session_key(cli1_key, wrapped, os.urandom(16), ns)


def test_session_cipher_blocks_tamper_replay_reorder_reflection():
    key = os.urandom(32)
    th = os.urandom(32)
    c2s = SessionCipher(
        key, Direction.CLIENT_TO_SERVER, Direction.SERVER_TO_CLIENT, th
    )
    s2c = SessionCipher(
        key, Direction.SERVER_TO_CLIENT, Direction.CLIENT_TO_SERVER, th
    )

    seq0, ct0 = c2s.encrypt_frame(b'{"resource":"fighters","action":"list"}')
    assert seq0 == 0
    assert (
        s2c.decrypt_frame(seq0, ct0)
        == b'{"resource":"fighters","action":"list"}'
    )

    # 1. Replay of seq=0 must fail
    with pytest.raises(
        CipherIntegrityError, match="Unexpected frame sequence"
    ):
        s2c.decrypt_frame(seq0, ct0)

    # 2. Reflection attack (sending C->S ciphertext back into C's receiver)
    # must fail
    seq1, ct1 = c2s.encrypt_frame(
        b'{"resource":"tournaments","action":"list"}'
    )
    with pytest.raises(
        CipherIntegrityError, match="authentication tag verification failed"
    ):
        c2s.decrypt_frame(seq0, ct0)

    # 3. 1-bit flip in ciphertext must fail GCM tag verification
    tampered = bytes([ct1[0] ^ 0x80]) + ct1[1:]
    with pytest.raises(
        CipherIntegrityError, match="authentication tag verification failed"
    ):
        s2c.decrypt_frame(seq1, tampered)

    # 4. Out-of-order sequence jump must fail
    seq2, ct2 = c2s.encrypt_frame(b'{"resource":"matches","action":"list"}')
    with pytest.raises(
        CipherIntegrityError, match="Unexpected frame sequence"
    ):
        s2c.decrypt_frame(seq2, ct2)


def test_session_cipher_rejects_mismatched_transcript_hash():
    key = os.urandom(32)
    c2s = SessionCipher(
        key, Direction.CLIENT_TO_SERVER, Direction.SERVER_TO_CLIENT, b"A" * 32
    )
    s2c = SessionCipher(
        key, Direction.SERVER_TO_CLIENT, Direction.CLIENT_TO_SERVER, b"B" * 32
    )

    seq, ct = c2s.encrypt_frame(b"hello")
    with pytest.raises(CipherIntegrityError):
        s2c.decrypt_frame(seq, ct)


# ---------------------------------------------------------------------------
# 3. End-to-End TCP Client <-> Server Security Integration Tests
# ---------------------------------------------------------------------------


async def test_e2e_sync_gateway_mutual_auth_and_encrypted_crud(
    secure_server, client1_security
):
    host, port = secure_server

    def _run_sync():
        with ServerGateway(
            host=host, port=port, security=client1_security
        ) as gw:
            assert gw.session is not None
            assert gw.session.peer_common_name == "tournament-server"
            created = gw.fighters.create(
                first_name="Helio",
                last_name="Gracie",
                birth_date="1913-10-01",
                gender="M",
                belt_level="black",
                club_name="Gracie Humaita",
                country="Brazil",
                email="helio@example.com",
            )
            fetched = gw.fighters.get(created["fighter_id"])
            return created, fetched

    created, fetched = await asyncio.to_thread(_run_sync)
    assert fetched is not None
    assert fetched["first_name"] == "Helio"
    assert fetched["last_name"] == "Gracie"


async def test_e2e_async_gateway_mutual_auth_and_encrypted_requests(
    secure_server, client2_security
):
    host, port = secure_server

    async with AsyncServerGateway(
        host=host, port=port, security=client2_security
    ) as gw:
        assert gw.session is not None
        assert gw.session.peer_common_name == "tournament-server"
        fighters = await gw.request("fighters", "list")
        tournaments = await gw.request("tournaments", "list")
        assert isinstance(fighters, list)
        assert isinstance(tournaments, list)


async def test_e2e_rejects_rogue_and_expired_clients(secure_server):
    host, port = secure_server

    rogue_sec = ClientSecurityConfig.from_files(
        cert_path=ROGUE_CERT_PATH,
        key_path=ROGUE_KEY_PATH,
        ca_path=CA_PATH,
        server_hostname="localhost",
    )
    expired_sec = ClientSecurityConfig.from_files(
        cert_path=EXPIRED_CERT_PATH,
        key_path=EXPIRED_KEY_PATH,
        ca_path=CA_PATH,
        server_hostname="localhost",
    )

    def _try_connect(sec: ClientSecurityConfig):
        with ServerGateway(host=host, port=port, security=sec) as gw:
            gw.fighters.list_all()

    with pytest.raises(ConnectionFailedError, match="AUTH_FAILED"):
        await asyncio.to_thread(_try_connect, rogue_sec)

    with pytest.raises(ConnectionFailedError, match="AUTH_FAILED"):
        await asyncio.to_thread(_try_connect, expired_sec)


async def test_e2e_client_rejects_server_hostname_mismatch(secure_server):
    host, port = secure_server
    bad_host_sec = ClientSecurityConfig.from_files(
        cert_path=CLI1_CERT_PATH,
        key_path=CLI1_KEY_PATH,
        ca_path=CA_PATH,
        server_hostname="not-in-san.local",
    )

    def _try_connect():
        with ServerGateway(host=host, port=port, security=bad_host_sec) as gw:
            gw.fighters.list_all()

    with pytest.raises(
        ConnectionFailedError, match="not present in certificate SAN"
    ):
        await asyncio.to_thread(_try_connect)


async def test_e2e_rejects_unencrypted_plaintext_client(secure_server):
    host, port = secure_server

    def _plain_probe():
        with socket.create_connection((host, port), timeout=5.0) as s:
            send_message(
                s, {"resource": "fighters", "action": "list", "payload": {}}
            )
            return receive_message(s)

    resp = await asyncio.to_thread(_plain_probe)
    assert resp["success"] is False
    assert resp["error_code"] == ErrorCode.AUTH_FAILED


async def test_e2e_mitm_bit_flip_detected_and_closes_session(
    secure_server, client1_security
):
    """Active MitM proxy flips 1 bit on the 5th wire frame (first encrypted
    request)."""
    target_host, target_port = secure_server
    frame_counter = 0

    async def _mitm_client(
        c_reader: asyncio.StreamReader, c_writer: asyncio.StreamWriter
    ) -> None:
        nonlocal frame_counter
        s_reader, s_writer = await asyncio.open_connection(
            target_host, target_port
        )

        async def _pipe(
            src: asyncio.StreamReader,
            dst: asyncio.StreamWriter,
            tamper_c2s: bool,
        ) -> None:
            nonlocal frame_counter
            try:
                while True:
                    hdr = await src.readexactly(HEADER_SIZE)
                    (length,) = struct.unpack("!I", hdr)
                    body = bytearray(await src.readexactly(length))
                    if tamper_c2s:
                        frame_counter += 1
                        # Frames 1 and 2 from client are M1 (ClientHello) and
                        # M3 (ClientProof).
                        # Frame 3 from client is the first AES-256-GCM
                        # application request.
                        if frame_counter == 3 and len(body) > 12:
                            body[-1] ^= 0x01
                    dst.write(hdr + bytes(body))
                    await dst.drain()
            except (asyncio.IncompleteReadError, ConnectionError, OSError):
                pass
            finally:
                if not dst.is_closing():
                    dst.close()

        await asyncio.gather(
            _pipe(c_reader, s_writer, tamper_c2s=True),
            _pipe(s_reader, c_writer, tamper_c2s=False),
        )

    mitm_server = await asyncio.start_server(_mitm_client, "127.0.0.1", 0)
    mitm_port = mitm_server.sockets[0].getsockname()[1]

    try:

        def _client_call():
            with ServerGateway(
                host="127.0.0.1", port=mitm_port, security=client1_security
            ) as gw:
                return gw.fighters.list_all()

        with pytest.raises(ServerError) as exc_info:
            await asyncio.to_thread(_client_call)
        assert exc_info.value.code == ErrorCode.INTEGRITY_ERROR
    finally:
        mitm_server.close()
        await mitm_server.wait_closed()


async def test_e2e_concurrent_authenticated_clients_isolated_sessions(
    secure_server, client1_security, client2_security
):
    host, port = secure_server

    async def _worker(idx: int, sec: ClientSecurityConfig) -> dict:
        async with AsyncServerGateway(
            host=host, port=port, security=sec
        ) as gw:
            created = await gw.request(
                "fighters",
                "create",
                {
                    "first_name": f"Fighter{idx}",
                    "last_name": "Secure",
                    "birth_date": "1998-05-12",
                    "gender": "M",
                    "belt_level": "blue",
                    "club_name": "Teknos BJJ",
                    "country": "Spain",
                    "email": f"fighter{idx}@example.com",
                },
            )
            listing = await gw.request("fighters", "list")
            assert any(
                f["fighter_id"] == created["fighter_id"] for f in listing
            )
            return created

    results = await asyncio.gather(
        *[
            _worker(i, client1_security if i % 2 == 0 else client2_security)
            for i in range(6)
        ]
    )
    assert len(results) == 6
    assert len({r["fighter_id"] for r in results}) == 6
