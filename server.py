"""Server entry point: start the concurrent asyncio TCP server."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from types import FrameType

from src.common.handshake import ServerSecurityConfig
from src.domain.db import Session, engine
from src.server.app import (
    DEFAULT_CLIENT_TIMEOUT,
    DEFAULT_DB_WORKERS,
    DEFAULT_HOST,
    DEFAULT_MAX_CONNECTIONS,
    DEFAULT_PORT,
    run_server,
)

log = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    """Parse command-line options for the TCP server."""
    parser = argparse.ArgumentParser(
        description="Tournament Back-Office TCP Server (asyncio)."
    )
    parser.add_argument(
        "--host",
        default=os.getenv("SERVER_HOST", DEFAULT_HOST),
        help=f"Bind address (default: {DEFAULT_HOST}).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("SERVER_PORT", str(DEFAULT_PORT))),
        help=f"Bind port (default: {DEFAULT_PORT}).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_DB_WORKERS,
        help=f"Database worker threads (default: {DEFAULT_DB_WORKERS}).",
    )
    parser.add_argument(
        "--max-connections",
        type=int,
        default=DEFAULT_MAX_CONNECTIONS,
        help=(
            "Maximum concurrent client connections "
            f"(default: {DEFAULT_MAX_CONNECTIONS})."
        ),
    )
    parser.add_argument(
        "--client-timeout",
        type=float,
        default=DEFAULT_CLIENT_TIMEOUT,
        help=(
            "Idle client timeout in seconds "
            f"(default: {DEFAULT_CLIENT_TIMEOUT})."
        ),
    )
    parser.add_argument(
        "--cert",
        default=os.getenv("SERVER_CERT_PATH", "certs/server/server.pem"),
        help=(
            "Path to server X.509 certificate PEM (default: "
            "certs/server/server.pem)."
        ),
    )
    parser.add_argument(
        "--key",
        default=os.getenv("SERVER_KEY_PATH", "certs/server/server.key"),
        help=(
            "Path to server RSA private key PEM (default: "
            "certs/server/server.key)."
        ),
    )
    parser.add_argument(
        "--ca",
        default=os.getenv("CA_CERT_PATH", "certs/ca/ca.pem"),
        help=(
            "Path to trusted Root CA certificate PEM (default: "
            "certs/ca/ca.pem)."
        ),
    )
    parser.add_argument(
        "--handshake-timeout",
        type=float,
        default=10.0,
        help=(
            "Maximum seconds allowed for mutual PKI handshake (default: "
            "10.0)."
        ),
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO).",
    )
    return parser.parse_args()


def _install_signal_handlers(
    loop: asyncio.AbstractEventLoop,
    stop_event: asyncio.Event,
) -> None:
    """Register SIGINT and SIGTERM handlers across POSIX and Windows."""

    def _trigger_shutdown() -> None:
        if not stop_event.is_set():
            log.info("Shutdown signal received; stopping server...")
            stop_event.set()

    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, _trigger_shutdown)
        except NotImplementedError:
            # Windows ProactorEventLoop does not support add_signal_handler.
            def _sync_handler(
                _signum: int,
                _frame: FrameType | None,
            ) -> None:
                loop.call_soon_threadsafe(_trigger_shutdown)

            signal.signal(sig, _sync_handler)


async def _serve(
    args: argparse.Namespace,
    security: ServerSecurityConfig,
) -> None:
    """Configure signal hooks and run the server until stopped."""
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    _install_signal_handlers(loop, stop_event)

    try:
        await run_server(
            host=args.host,
            port=args.port,
            session_factory=Session,
            db_workers=args.workers,
            client_timeout=args.client_timeout,
            max_connections=args.max_connections,
            stop_event=stop_event,
            security=security,
        )
    finally:
        log.info("Disposing SQLAlchemy connection pool...")
        engine.dispose()
        log.info("Server shutdown complete.")


def main() -> None:
    """Entry point invoked when running ``python server.py``."""
    args = _parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    try:
        security = ServerSecurityConfig.from_files(
            cert_path=args.cert,
            key_path=args.key,
            ca_path=args.ca,
            handshake_timeout=args.handshake_timeout,
        )
    except Exception as exc:
        log.error("Failed to load server PKI credentials: %s", exc)
        sys.exit(2)

    try:
        asyncio.run(_serve(args, security))
    except KeyboardInterrupt:
        log.info("Interrupted by user; exiting.")


if __name__ == "__main__":
    main()
