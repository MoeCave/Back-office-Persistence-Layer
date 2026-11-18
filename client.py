"""client.py — Punto de entrada ejecutable del cliente TCP de consola.

Uso:
    python client.py
    python client.py --host 127.0.0.1 --port 9000 \\
                     --cert certs/client1/client1.pem \\
                     --key certs/client1/client1.key \\
                     --ca certs/ca/ca.pem

Flujo de ejecución:
1. Configura credenciales PKI del cliente (certificado X.509 y clave privada).
2. Conecta por TCP al servidor y ejecuta el handshake mutuo (M1->M4).
3. Tras autenticarse y negociar clave simétrica AES-256-GCM, inicia los menús.
4. Desacoplado por completo de SQLAlchemy: solo interactúa con ServerGateway.
"""

from __future__ import annotations

import argparse
import os
import sys

from src.client.gateway import ConnectionFailedError, ServerGateway
from src.client.ui.console import console
from src.client.ui.main_menu import run_main_menu
from src.common.handshake import ClientSecurityConfig


def main() -> None:
    """Punto de entrada del cliente interactivo TCP.

    Parsea argumentos CLI, carga credenciales PKI del cliente y del CA,
    establece la conexión segura autenticada mediante ServerGateway y ejecuta
    el menú interactivo de la consola Rich. Maneja interrupciones y fallos de
    red informando limpiamente en pantalla.
    """
    parser = argparse.ArgumentParser(
        description="Tournament Back-Office TCP Client"
    )
    parser.add_argument("--host", default="127.0.0.1", help="Server host")
    parser.add_argument("--port", type=int, default=9000, help="Server port")
    parser.add_argument(
        "--cert",
        default=os.getenv("CLIENT_CERT_PATH", "certs/client1/client1.pem"),
        help=(
            "Path to client X.509 certificate PEM (default: "
            "certs/client1/client1.pem)"
        ),
    )
    parser.add_argument(
        "--key",
        default=os.getenv("CLIENT_KEY_PATH", "certs/client1/client1.key"),
        help=(
            "Path to client RSA private key PEM (default: "
            "certs/client1/client1.key)"
        ),
    )
    parser.add_argument(
        "--ca",
        default=os.getenv("CA_CERT_PATH", "certs/ca/ca.pem"),
        help=(
            "Path to trusted Root CA certificate PEM (default: "
            "certs/ca/ca.pem)"
        ),
    )
    parser.add_argument(
        "--server-hostname",
        default=os.getenv("SERVER_HOSTNAME", "localhost"),
        help="Expected server SAN hostname/IP (default: localhost)",
    )
    parser.add_argument(
        "--handshake-timeout",
        type=float,
        default=10.0,
        help="Maximum seconds allowed for mutual handshake (default: 10.0)",
    )
    args = parser.parse_args()

    try:
        security = ClientSecurityConfig.from_files(
            cert_path=args.cert,
            key_path=args.key,
            ca_path=args.ca,
            server_hostname=args.server_hostname,
            handshake_timeout=args.handshake_timeout,
        )
    except Exception as exc:
        console.print(
            f"[error]  Failed to load client PKI credentials: {exc}[/]"
        )
        sys.exit(2)

    try:
        with ServerGateway(
            host=args.host, port=args.port, security=security
        ) as gw:
            peer_cn = (
                gw.session.peer_common_name
                if gw.session is not None
                else "unknown"
            )
            console.print(
                f"[success]  Connected securely to {args.host}:{args.port} "
                f"(verified server CN={peer_cn!r}, AES-256-GCM)[/]"
            )
            run_main_menu(gw)
    except ConnectionError as exc:
        console.print(f"[error]  Connection to the server lost: {exc}[/]")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[info]  Interrupted by user.[/]")
    except ConnectionFailedError as exc:
        console.print(f"[error]  {exc}[/]")
        console.print("[info]  Start the server with:  python server.py[/]")
        sys.exit(1)


if __name__ == "__main__":
    main()
