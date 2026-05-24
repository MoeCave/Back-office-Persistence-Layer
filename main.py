"""
main.py — application entry point.


Usage:
    docker compose up -d
    python main.py

"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from src.domain.db import Session, engine, Base
import src.domain.models

from src.ui.main_menu import run_main_menu
from src.ui.console import console


def _ensure_schema() -> None:
    Base.metadata.create_all(engine)


def main() -> None:
    try:
        _ensure_schema()
    except Exception as exc:
        console.print(f"[error]  Could not connect to the database: {exc}[/]")
        console.print("[info]  Make sure your .env is configured and Docker is running.[/]")
        console.print("[info]  For a quick start without Docker: APP_ENV=test python main.py[/]")
        sys.exit(1)

    run_main_menu(session_factory=Session)


if __name__ == "__main__":
    main()
