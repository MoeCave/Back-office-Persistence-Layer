"""End-to-end concurrent integration tests with real SQLAlchemy sessions."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.client.async_gateway import AsyncServerError, AsyncServerGateway
from src.common.protocol import ErrorCode
from src.domain.db import Base
from src.server.app import run_server

import pytest


def _build_file_session_factory(db_path: Path):
    """Create a thread-safe SQLite file engine and sessionmaker."""
    url = f"sqlite:///{db_path.as_posix()}"
    eng = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(eng)
    return eng, sessionmaker(bind=eng, expire_on_commit=False)


async def test_end_to_end_concurrent_queries_across_resources(
    tmp_path: Path,
) -> None:
    """Multiple async clients query all resources concurrently via ORM."""
    eng, session_factory = _build_file_session_factory(
        tmp_path / "e2e_concurrent.db"
    )
    stop_event = asyncio.Event()
    started = asyncio.Event()
    bound: dict[str, Any] = {}

    def _on_started(host: str, port: int) -> None:
        bound["host"] = host
        bound["port"] = port
        started.set()

    server_task = asyncio.create_task(
        run_server(
            host="127.0.0.1",
            port=0,
            session_factory=session_factory,
            db_workers=4,
            stop_event=stop_event,
            on_started=_on_started,
        )
    )
    await asyncio.wait_for(started.wait(), timeout=5.0)

    resources = [
        "fighters",
        "tournaments",
        "categories",
        "matches",
        "registrations",
    ]

    async def _query_resource(res_name: str) -> tuple[str, list[Any]]:
        async with AsyncServerGateway(bound["host"], bound["port"]) as gw:
            rows = await gw.resource(res_name).call("list")
            return res_name, rows

    try:
        # Launch 15 concurrent clients (3 per resource) simultaneously.
        tasks = [
            _query_resource(resources[i % len(resources)]) for i in range(15)
        ]
        results = await asyncio.gather(*tasks)
        assert len(results) == 15
        for _, rows in results:
            assert isinstance(rows, list)

        # Verify NOT_FOUND propagates cleanly from service to client.
        async with AsyncServerGateway(bound["host"], bound["port"]) as gw:
            with pytest.raises(AsyncServerError) as exc_info:
                await gw.resource("fighters").call(
                    "get", {"fighter_id": 999999}
                )
            assert exc_info.value.code == ErrorCode.NOT_FOUND
    finally:
        stop_event.set()
        await asyncio.wait_for(server_task, timeout=5.0)
        eng.dispose()
