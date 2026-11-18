"""Cryptographic primitives for mutual certificate authentication and AES-GCM.

Primitivas criptográficas para autenticación mutua y cifrado de sesión.
Implementa:
- Validación de certificados X.509 v3 frente a Root CA (firma, validez UTC,
  BasicConstraints ca=False, ExtendedKeyUsage y SAN).
- Firmas RSA-PSS (SHA-256, MGF1, sal máxima) para prueba de posesión (M2, M3).
- Transporte de clave de sesión efímera con RSA-OAEP (SHA-256, MGF1)
  vinculando K_ses || nonce_c || nonce_s.
- Canal simétrico autenticado con AES-256-GCM, contadores monótonos de 64 bits
  independientes por dirección y AAD ligado al transcript del handshake.
"""

from __future__ import annotations

import datetime as dt
import ipaddress
import struct
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from cryptography import x509
from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

# Protocol cryptographic constants
AES_KEY_SIZE = 32  # 256-bit AES key
NONCE_SIZE = 16  # 128-bit handshake random nonce
GCM_NONCE_SIZE = 12  # 96-bit AES-GCM nonce (4B direction + 8B uint64 seq)
GCM_TAG_SIZE = 16  # 128-bit AES-GCM authentication tag
SESSION_BLOB_SIZE = AES_KEY_SIZE + (
    2 * NONCE_SIZE
)  # 64 bytes: key || nonce_c || nonce_s
MAX_SEQUENCE_NUMBER = (1 << 64) - 1


class CryptoError(Exception):
    """Base exception for all cryptographic and authentication failures."""


class CertificateValidationError(CryptoError):
    """Raised when an X.509 certificate fails CA, temporal, EKU, or SAN
    checks."""


class HandshakeCryptoError(CryptoError):
    """Raised when handshake signature verification or key unwrapping fails."""


class CipherIntegrityError(CryptoError):
    """Raised when AES-256-GCM decryption, tag verification, or sequence check
    fails."""


class Direction(Enum):
    """Traffic direction identifier used in GCM nonces and AAD."""

    CLIENT_TO_SERVER = b"C2S\x00"
    SERVER_TO_CLIENT = b"S2C\x00"


# ---------------------------------------------------------------------------
# PEM loading helpers
# ---------------------------------------------------------------------------


def load_certificate_pem(data: bytes) -> x509.Certificate:
    """Parse a PEM-encoded X.509 certificate."""
    try:
        return x509.load_pem_x509_certificate(data)
    except Exception as exc:
        raise CertificateValidationError(
            f"Invalid PEM certificate: {exc}"
        ) from exc


def load_certificate_file(path: Path | str) -> x509.Certificate:
    """Read and parse a PEM-encoded X.509 certificate from disk."""
    return load_certificate_pem(Path(path).read_bytes())


def load_private_key_file(
    path: Path | str,
    password: bytes | None = None,
) -> rsa.RSAPrivateKey:
    """Read and parse a PEM-encoded RSA private key from disk."""
    try:
        key = serialization.load_pem_private_key(
            Path(path).read_bytes(), password=password
        )
    except Exception as exc:
        raise CryptoError(
            f"Failed to load private key from '{path}': {exc}"
        ) from exc
    if not isinstance(key, rsa.RSAPrivateKey):
        raise CryptoError(
            f"Expected an RSA private key in '{path}', got "
            f"{type(key).__name__}"
        )
    return key


def extract_common_name(cert: x509.Certificate) -> str:
    """Return the first Common Name (CN) attribute of a certificate subject, or
    empty string."""
    attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    return str(attrs[0].value) if attrs else ""


def certificate_fingerprint_sha256(cert: x509.Certificate) -> str:
    """Return lowercase hex SHA-256 fingerprint of a certificate."""
    return cert.fingerprint(hashes.SHA256()).hex()


# ---------------------------------------------------------------------------
# X.509 certificate validation
# ---------------------------------------------------------------------------


def validate_peer_certificate(
    cert: x509.Certificate,
    ca_cert: x509.Certificate,
    *,
    expect_server: bool,
    expected_hostname: str | None = None,
    now: dt.datetime | None = None,
) -> rsa.RSAPublicKey:
    """Valida un certificado X.509 de entidad final contra la Root CA.

    Comprobaciones realizadas:
    1. Issuer DN coincide con el Subject de la CA.
    2. La firma del certificado valida bajo la clave pública de la CA.
    3. Fecha UTC dentro de [not_valid_before_utc, not_valid_after_utc].
    4. BasicConstraints está presente y declara ca=False.
    5. ExtendedKeyUsage contiene SERVER_AUTH o CLIENT_AUTH.
    6. Coincidencia de SAN (DNSName o IPAddress) para el servidor.
    7. Clave pública RSA con al menos 2048 bits.

    Retorna la clave pública RSA validada del interlocutor.
    """
    # 1. Issuer coincide con el Subject de la CA raíz
    if cert.issuer != ca_cert.subject:
        raise CertificateValidationError(
            f"Certificate issuer '{cert.issuer.rfc4514_string()}' does not "
            f"match trusted CA '{ca_cert.subject.rfc4514_string()}'"
        )

    # 2. Verificación de la firma con la clave pública de la CA
    try:
        cert.verify_directly_issued_by(ca_cert)
    except Exception as exc:
        raise CertificateValidationError(
            f"Certificate signature verification against CA failed: {exc}"
        ) from exc

    # 3. Ventana temporal de validez en UTC
    check_time = now or dt.datetime.now(dt.timezone.utc)
    if check_time < cert.not_valid_before_utc:
        raise CertificateValidationError(
            f"Certificate is not valid yet (starts "
            f"{cert.not_valid_before_utc.isoformat()})"
        )
    if check_time > cert.not_valid_after_utc:
        raise CertificateValidationError(
            f"Certificate expired on {cert.not_valid_after_utc.isoformat()}"
        )

    # 4. BasicConstraints prohíbe ca=True en entidades finales
    try:
        bc = cert.extensions.get_extension_for_class(
            x509.BasicConstraints
        ).value
    except x509.ExtensionNotFound as exc:
        raise CertificateValidationError(
            "Certificate missing BasicConstraints extension"
        ) from exc
    if bc.ca:
        raise CertificateValidationError(
            "End-entity certificate cannot have BasicConstraints ca=True"
        )

    # 5. Control de roles mediante ExtendedKeyUsage
    try:
        eku = cert.extensions.get_extension_for_class(
            x509.ExtendedKeyUsage
        ).value
    except x509.ExtensionNotFound as exc:
        raise CertificateValidationError(
            "Certificate missing ExtendedKeyUsage extension"
        ) from exc

    required_oid = (
        ExtendedKeyUsageOID.SERVER_AUTH
        if expect_server
        else ExtendedKeyUsageOID.CLIENT_AUTH
    )
    if required_oid not in eku:
        role = "serverAuth" if expect_server else "clientAuth"
        raise CertificateValidationError(
            f"Certificate ExtendedKeyUsage lacks required '{role}'"
        )

    # 6. Verificación de SAN (DNS e IP)
    if expected_hostname is not None:
        _verify_san_hostname(cert, expected_hostname)

    # 7. Algoritmo y fortaleza mínima de la clave pública
    pub_key = cert.public_key()
    if not isinstance(pub_key, rsa.RSAPublicKey):
        raise CertificateValidationError(
            f"Unsupported public key algorithm: {type(pub_key).__name__} "
            f"(expected RSA)"
        )
    if pub_key.key_size < 2048:
        raise CertificateValidationError(
            f"RSA key size {pub_key.key_size} bits is below minimum 2048 bits"
        )

    return pub_key


def _verify_san_hostname(cert: x509.Certificate, hostname: str) -> None:
    """Verify `hostname` against SubjectAlternativeName DNSName or IPAddress
    entries."""
    try:
        san = cert.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value
    except x509.ExtensionNotFound as exc:
        raise CertificateValidationError(
            "Server certificate missing SubjectAlternativeName extension"
        ) from exc

    normalized = hostname.strip().lower()
    try:
        ip_obj = ipaddress.ip_address(normalized)
    except ValueError:
        ip_obj = None

    if ip_obj is not None:
        valid_ips = san.get_values_for_type(x509.IPAddress)
        if ip_obj not in valid_ips:
            raise CertificateValidationError(
                f"Server IP '{hostname}' not present in certificate SAN "
                f"IPAddresses"
            )
    else:
        valid_dns = [d.lower() for d in san.get_values_for_type(x509.DNSName)]
        if normalized not in valid_dns:
            raise CertificateValidationError(
                f"Server hostname '{hostname}' not present in certificate "
                f"SAN DNSNames {valid_dns}"
            )


# ---------------------------------------------------------------------------
# Handshake signatures (RSA-PSS) & session key transport (RSA-OAEP)
# ---------------------------------------------------------------------------


def sign_pss(private_key: rsa.RSAPrivateKey, data: bytes) -> bytes:
    """Sign `data` using RSA-PSS with SHA-256 and maximum salt length."""
    return private_key.sign(
        data,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )


def verify_pss(
    public_key: rsa.RSAPublicKey, signature: bytes, data: bytes
) -> None:
    """Verify an RSA-PSS (SHA-256) signature; raise `HandshakeCryptoError` on
    mismatch."""
    try:
        public_key.verify(
            signature,
            data,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
    except InvalidSignature as exc:
        raise HandshakeCryptoError(
            "RSA-PSS signature verification failed"
        ) from exc


def wrap_session_key(
    client_public_key: rsa.RSAPublicKey,
    session_key: bytes,
    nonce_c: bytes,
    nonce_s: bytes,
) -> bytes:
    """Cifra `session_key || nonce_c || nonce_s` con RSA-OAEP (SHA-256).

    Al empaquetar la clave simétrica junto a ambos nonces del handshake,
    se vincula el secreto de sesión a esta conexión exacta, impidiendo
    ataques de repetición o inyección de claves de sesiones previas.
    """
    if len(session_key) != AES_KEY_SIZE:
        raise ValueError(f"session_key must be {AES_KEY_SIZE} bytes")
    if len(nonce_c) != NONCE_SIZE or len(nonce_s) != NONCE_SIZE:
        raise ValueError(f"nonces must be {NONCE_SIZE} bytes each")

    payload = session_key + nonce_c + nonce_s
    return client_public_key.encrypt(
        payload,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )


def unwrap_session_key(
    client_private_key: rsa.RSAPrivateKey,
    encrypted_blob: bytes,
    expected_nonce_c: bytes,
    expected_nonce_s: bytes,
) -> bytes:
    """Descifra sobre RSA-OAEP y comprueba nonces del handshake actual."""
    try:
        payload = client_private_key.decrypt(
            encrypted_blob,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
    except Exception as exc:
        raise HandshakeCryptoError(
            "Failed to decrypt RSA-OAEP session key"
        ) from exc

    if len(payload) != SESSION_BLOB_SIZE:
        raise HandshakeCryptoError(
            f"Invalid decrypted session key blob length: {len(payload)} "
            f"(expected {SESSION_BLOB_SIZE})"
        )

    session_key = payload[:AES_KEY_SIZE]
    nonce_c = payload[AES_KEY_SIZE : AES_KEY_SIZE + NONCE_SIZE]
    nonce_s = payload[AES_KEY_SIZE + NONCE_SIZE :]

    # Verificar coincidencia estricta de nonces
    if nonce_c != expected_nonce_c or nonce_s != expected_nonce_s:
        raise HandshakeCryptoError(
            "Session key nonces do not match current handshake"
        )

    return session_key


# ---------------------------------------------------------------------------
# Canal simétrico autenticado de sesión (AES-256-GCM)
# ---------------------------------------------------------------------------


@dataclass
class SessionCipher:
    """Cifrador de sesión simétrico y con estado basado en AES-256-GCM.

    Mantiene contadores monótonos de secuencia de 64 bits independientes para
    tramas salientes (`send_seq`) y entrantes (`recv_seq`).
    Garantiza:
    - Confidencialidad e integridad autenticada (tag GCM de 128 bits).
    - Prevención de ataques de reproducción (replay) y reordenación.
    - Prevención de ataques de reflexión (etiquetas direccionales C2S y S2C).
    - Autenticación del transcript del handshake como AAD.
    """

    session_key: bytes
    send_direction: Direction
    recv_direction: Direction
    transcript_hash: bytes = b""
    send_seq: int = 0
    recv_seq: int = 0

    def __post_init__(self) -> None:
        if len(self.session_key) != AES_KEY_SIZE:
            raise ValueError(f"AES-256-GCM requires a {AES_KEY_SIZE}-byte key")
        if self.send_direction == self.recv_direction:
            raise ValueError(
                "send_direction and recv_direction must be distinct"
            )
        self._aesgcm = AESGCM(self.session_key)

    @staticmethod
    def _build_nonce(direction: Direction, seq: int) -> bytes:
        """Construye un nonce de 96 bits: 4B dirección + 8B contador uint64."""
        if not (0 <= seq <= MAX_SEQUENCE_NUMBER):
            raise CipherIntegrityError(f"Sequence number out of bounds: {seq}")
        return direction.value + struct.pack(">Q", seq)

    def _build_aad(self, direction: Direction, seq: int) -> bytes:
        """Construye AAD: dirección + seq + hash acumulado de transcript."""
        return direction.value + struct.pack(">Q", seq) + self.transcript_hash

    def encrypt_frame(self, plaintext: bytes) -> tuple[int, bytes]:
        """Cifra el texto plano bajo el siguiente número de secuencia.

        Retorna `(seq, ciphertext_with_tag)` e incrementa `self.send_seq`.
        """
        seq = self.send_seq
        nonce = self._build_nonce(self.send_direction, seq)
        aad = self._build_aad(self.send_direction, seq)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext, aad)
        self.send_seq = seq + 1
        return seq, ciphertext

    def decrypt_frame(self, seq: int, ciphertext: bytes) -> bytes:
        """Verifica `seq == self.recv_seq` y descifra con AES-256-GCM.

        Lanza `CipherIntegrityError` si la secuencia no es la esperada
        o si el tag GCM de 128 bits falla la verificación de integridad.
        """
        if seq != self.recv_seq:
            raise CipherIntegrityError(
                f"Unexpected frame sequence number: got {seq}, expected "
                f"{self.recv_seq}"
            )
        nonce = self._build_nonce(self.recv_direction, seq)
        aad = self._build_aad(self.recv_direction, seq)
        try:
            plaintext = self._aesgcm.decrypt(nonce, ciphertext, aad)
        except InvalidTag as exc:
            raise CipherIntegrityError(
                f"AES-256-GCM authentication tag verification failed at "
                f"seq={seq}"
            ) from exc
        self.recv_seq = seq + 1
        return plaintext
