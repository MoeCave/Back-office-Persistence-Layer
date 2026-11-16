"""Async SQLAlchemy 2.0 vertical slice (engine, UoW, and repository).

Demonstrates native ``asyncio`` persistence using ``AsyncSession`` and
``async_sessionmaker`` without offloading queries to worker threads.
"""

from __future__ import annotations

from collections.abc import Sequence
from types import TracebackType

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.domain.models import Fighter


class AsyncFighterRepository:
    """Asynchronous repository for :class:`Fighter` entities."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, fighter: Fighter) -> Fighter:
        """Stage *fighter* in the current async session."""
        self._session.add(fighter)
        await self._session.flush()
        return fighter

    async def get_by_id(self, fighter_id: int) -> Fighter | None:
        """Fetch a single fighter by primary key."""
        stmt = select(Fighter).where(Fighter.fighter_id == fighter_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self) -> Sequence[Fighter]:
        """Return all fighters ordered by ``fighter_id``."""
        stmt = select(Fighter).order_by(Fighter.fighter_id)
        result = await self._session.execute(stmt)
        return result.scalars().all()


class AsyncUnitOfWork:
    """Async context manager wrapping an :class:`AsyncSession`."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory
        self.session: AsyncSession | None = None
        self.fighters: AsyncFighterRepository

    async def __aenter__(self) -> AsyncUnitOfWork:
        self.session = self._session_factory()
        self.fighters = AsyncFighterRepository(self.session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self.session is None:
            return
        try:
            if exc_type is None:
                await self.session.commit()
            else:
                await self.session.rollback()
        finally:
            await self.session.close()


def build_async_session_factory(
    async_url: str,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Create an :class:`AsyncEngine` and ``AsyncSession`` factory."""
    engine = create_async_engine(async_url, future=True)
    factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return engine, factory
