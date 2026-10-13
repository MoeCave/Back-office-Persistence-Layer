"""
server.py — runnable TCP server entry point.

Usage:
    python server.py
    python server.py --host 0.0.0.0 --port 9000
    APP_ENV=test python server.py
"""

from __future__ import annotations

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from src.domain.db import Session, engine, Base
from src.server.app import run_server, DEFAULT_HOST, DEFAULT_PORT


def _ensure_schema() -> None:
    Base.metadata.create_all(engine)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tournament Back-Office TCP Server"
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind address")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Bind port")
    args = parser.parse_args()

    try:
        _ensure_schema()
    except Exception as exc:
        print(f"[ERROR] Could not connect to database: {exc}", file=sys.stderr)
        print(
            "[INFO]  Make sure Docker is running or set APP_ENV=test",
            file=sys.stderr,
        )
        sys.exit(1)

    run_server(host=args.host, port=args.port, session_factory=Session)


if __name__ == "__main__":
    main()
