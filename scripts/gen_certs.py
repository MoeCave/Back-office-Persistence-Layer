"""Generate a local PKI (Root CA, server, clients, and negative-test
certificates).

Creates X.509 v3 certificates signed with RSA-3072 + SHA-256 (PKCS#1 v1.5 for
X.509
compatibility across OpenSSL/cryptography, while handshake signatures use
RSA-PSS).

Usage:
    python scripts/gen_certs.py
    python scripts/gen_certs.py --out-dir certs --force
"""

from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import os
import stat
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

RSA_KEY_SIZE = 3072
RSA_PUBLIC_EXPONENT = 65537


def _generate_rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(
        public_exponent=RSA_PUBLIC_EXPONENT,
        key_size=RSA_KEY_SIZE,
    )


def _build_name(
    common_name: str, organization: str = "Tournament Manager PKI"
) -> x509.Name:
    return x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "ES"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )


def _write_pem_pair(
    directory: Path,
    stem: str,
    cert: x509.Certificate,
    private_key: rsa.RSAPrivateKey,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    cert_path = directory / f"{stem}.pem"
    key_path = directory / f"{stem}.key"

    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    # Restrict private key file permissions to owner read/write (0600) on POSIX
    try:
        os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def create_ca(
    common_name: str = "Tournament Manager Root CA",
    valid_days: int = 3650,
) -> tuple[x509.Certificate, rsa.RSAPrivateKey]:
    """Create a self-signed Root CA certificate and private key."""
    key = _generate_rsa_key()
    subject = issuer = _build_name(common_name)
    now = dt.datetime.now(dt.timezone.utc)

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=valid_days))
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=0), critical=True
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
            critical=False,
        )
        .sign(private_key=key, algorithm=hashes.SHA256())
    )
    return cert, key


def issue_end_entity_cert(
    *,
    common_name: str,
    ca_cert: x509.Certificate,
    ca_key: rsa.RSAPrivateKey,
    is_server: bool,
    san_dns: list[str] | None = None,
    san_ips: list[str] | None = None,
    not_valid_before: dt.datetime | None = None,
    not_valid_after: dt.datetime | None = None,
) -> tuple[x509.Certificate, rsa.RSAPrivateKey]:
    """Issue a signed end-entity certificate (server or client)."""
    key = _generate_rsa_key()
    now = dt.datetime.now(dt.timezone.utc)
    valid_from = not_valid_before or (now - dt.timedelta(minutes=5))
    valid_until = not_valid_after or (now + dt.timedelta(days=365))

    eku_oid = (
        ExtendedKeyUsageOID.SERVER_AUTH
        if is_server
        else ExtendedKeyUsageOID.CLIENT_AUTH
    )

    builder = (
        x509.CertificateBuilder()
        .subject_name(_build_name(common_name))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(valid_from)
        .not_valid_after(valid_until)
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([eku_oid]), critical=False)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(
                ca_key.public_key()
            ),
            critical=False,
        )
    )

    san_entries: list[x509.GeneralName] = []
    for dns in san_dns or []:
        san_entries.append(x509.DNSName(dns))
    for ip in san_ips or []:
        san_entries.append(x509.IPAddress(ipaddress.ip_address(ip)))
    if san_entries:
        builder = builder.add_extension(
            x509.SubjectAlternativeName(san_entries),
            critical=False,
        )

    cert = builder.sign(private_key=ca_key, algorithm=hashes.SHA256())
    return cert, key


def generate_all(out_dir: Path, force: bool = False) -> None:
    """Generate the full local PKI directory layout."""
    ca_cert_file = out_dir / "ca" / "ca.pem"
    if ca_cert_file.exists() and not force:
        raise FileExistsError(
            f"Certificates already exist at '{out_dir}'. Pass --force to "
            f"overwrite."
        )

    # 1. Root CA
    ca_cert, ca_key = create_ca()
    _write_pem_pair(out_dir / "ca", "ca", ca_cert, ca_key)

    # 2. Server certificate (valid for localhost and 127.0.0.1)
    srv_cert, srv_key = issue_end_entity_cert(
        common_name="tournament-server",
        ca_cert=ca_cert,
        ca_key=ca_key,
        is_server=True,
        san_dns=["localhost"],
        san_ips=["127.0.0.1", "::1"],
    )
    _write_pem_pair(out_dir / "server", "server", srv_cert, srv_key)

    # 3. Valid Client 1 & Client 2
    for idx in (1, 2):
        cli_cert, cli_key = issue_end_entity_cert(
            common_name=f"client{idx}",
            ca_cert=ca_cert,
            ca_key=ca_key,
            is_server=False,
        )
        _write_pem_pair(
            out_dir / f"client{idx}", f"client{idx}", cli_cert, cli_key
        )

    # 4. Negative-test fixtures: rogue CA client & expired client
    rogue_ca_cert, rogue_ca_key = create_ca(common_name="Rogue Untrusted CA")
    rogue_cli_cert, rogue_cli_key = issue_end_entity_cert(
        common_name="rogue-client",
        ca_cert=rogue_ca_cert,
        ca_key=rogue_ca_key,
        is_server=False,
    )
    _write_pem_pair(
        out_dir / "test_invalid", "rogue_client", rogue_cli_cert, rogue_cli_key
    )

    now = dt.datetime.now(dt.timezone.utc)
    exp_cli_cert, exp_cli_key = issue_end_entity_cert(
        common_name="expired-client",
        ca_cert=ca_cert,
        ca_key=ca_key,
        is_server=False,
        not_valid_before=now - dt.timedelta(days=30),
        not_valid_after=now - dt.timedelta(days=1),
    )
    _write_pem_pair(
        out_dir / "test_invalid", "expired_client", exp_cli_cert, exp_cli_key
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate local X.509 certificates for Tournament Manager."
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("certs"),
        help="Output directory for generated certificates (default: certs)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing certificates if present",
    )
    args = parser.parse_args()
    generate_all(args.out_dir, force=args.force)
    print(f"PKI generated successfully under: {args.out_dir.resolve()}")


if __name__ == "__main__":
    main()
