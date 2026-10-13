"""
client.py — runnable TCP client entry point.

Usage:
    python client.py
    python client.py --host 127.0.0.1 --port 9000
"""

from __future__ import annotations

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from src.client.gateway import ServerGateway, ConnectionFailedError
from src.client.ui.main_menu import run_main_menu
from src.ui.console import console


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tournament Back-Office TCP Client"
    )
    parser.add_argument("--host", default="127.0.0.1", help="Server host")
    parser.add_argument("--port", type=int, default=9000, help="Server port")
    args = parser.parse_args()

    try:
        with ServerGateway(host=args.host, port=args.port) as gw:
            console.print(
                f"[success]  Connected to server at {args.host}:{args.port}[/]"
            )
            run_main_menu(gw)
    except ConnectionFailedError as exc:
        console.print(f"[error]  {exc}[/]")
        console.print("[info]  Start the server with:  python server.py[/]")
        sys.exit(1)


if __name__ == "__main__":
    main()
