"""Tests for the native Async SQLAlchemy 2.0 vertical slice."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

from src.domain.async_db import (
    AsyncUnitOfWork,
    build_async_session_factory,
)
from src.domain.db import Base
from src.domain.models import Fighter


async def test_async_uow_crud_and_no_missing_greenlet(
    tmp_path: Path,
) -> None:
    """Committed ORM attributes remain readable without lazy I/O."""
    db_file = tmp_path / "async_spike.db"
    engine, session_factory = build_async_session_factory(
        f"sqlite+aiosqlite:///{db_file.as_posix()}"
    )
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with AsyncUnitOfWork(session_factory) as uow:
            fighter = await uow.fighters.add(
                Fighter(
                    first_name="Khabib",
                    last_name="Nurmagomedov",
                    birth_date=date(1988, 9, 20),
                )
            )
            created_id = fighter.fighter_id

        # Accessing attributes after commit/close must not raise
        # MissingGreenlet thanks to expire_on_commit=False.
        assert created_id is not None
        assert fighter.first_name == "Khabib"

        async with AsyncUnitOfWork(session_factory) as uow:
            fetched = await uow.fighters.get_by_id(created_id)
            assert fetched is not None
            assert fetched.last_name == "Nurmagomedov"
    finally:
        await engine.dispose()


async def test_async_uow_concurrent_reads_on_single_event_loop(
    tmp_path: Path,
) -> None:
    """Multiple coroutines query SQLite concurrently without threads."""
    db_file = tmp_path / "async_concurrent.db"
    engine, session_factory = build_async_session_factory(
        f"sqlite+aiosqlite:///{db_file.as_posix()}"
    )
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with AsyncUnitOfWork(session_factory) as uow:
            for idx in range(5):
                await uow.fighters.add(
                    Fighter(
                        first_name=f"Async{idx}",
                        last_name="Tester",
                        birth_date=date(1995, 3, 10),
                    )
                )

        async def _read_all() -> int:
            async with AsyncUnitOfWork(session_factory) as uow:
                rows = await uow.fighters.list_all()
                return len(rows)

        counts = await asyncio.gather(*(_read_all() for _ in range(12)))
        assert counts == [5] * 12
    finally:
        await engine.dispose()
