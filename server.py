"""Runnable TCP server entry point.

Usage:
    python server.py
    python server.py --host 0.0.0.0 --port 9000
    APP_ENV=test python server.py
"""

from __future__ import annotations

import argparse
import logging
import sys

from src.common.protocol import DEFAULT_HOST, DEFAULT_PORT
from src.domain.db import Base, Session, engine
from src.server.app import DEFAULT_CLIENT_TIMEOUT, run_server


def _ensure_schema() -> None:
    """Create the tables if they do not exist yet."""
    Base.metadata.create_all(engine)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tournament Back-Office TCP Server"
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind address")
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help="Bind port"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_CLIENT_TIMEOUT,
        help="Seconds of client inactivity before dropping it (0 = never)",
    )
    parser.add_argument("--debug", action="store_true", help="Log requests")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [SERVER] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        _ensure_schema()
    except Exception as exc:  # noqa: BLE001 - report any startup failure
        print(f"[ERROR] Could not connect to database: {exc}", file=sys.stderr)
        print(
            "[INFO]  Make sure Docker is running or set APP_ENV=test",
            file=sys.stderr,
        )
        sys.exit(1)

    run_server(
        host=args.host,
        port=args.port,
        session_factory=Session,
        client_timeout=args.timeout or None,
    )


if __name__ == "__main__":
    main()
