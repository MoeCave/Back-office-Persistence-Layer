"""Generic base repository with shared CRUD operations."""

from datetime import datetime, timezone
from typing import Generic, List, Optional, Type, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.domain.db import Base

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    """CRUD operations shared by all concrete repositories.

    Subclasses inject the model class via the constructor so the base
    can build SELECT statements without knowing the concrete type.
    """

    def __init__(self, session: Session, model: Type[T]) -> None:
        self._session = session
        self._model = model

    # ── Create ─────────────────────────────────────────────────────────────────
    def add(self, entity: T) -> T:
        """Persist a new entity (added to the session; commit via UoW)."""
        self._session.add(entity)
        self._session.flush()
        return entity

    # ── Read ───────────────────────────────────────────────────────────────────
    def get(self, pk: int) -> Optional[T]:
        """Retrieve a single entity by its integer primary key."""
        return self._session.get(self._model, pk)

    def get_all(self) -> List[T]:
        """Retrieve all rows for this model."""
        stmt = select(self._model)
        return list(self._session.scalars(stmt).all())

    # ── Update ─────────────────────────────────────────────────────────────────
    def update(self, entity: T) -> T:
        """Merge an entity back into the session and refresh last_update.

        SQLAlchemy's onupdate hook fires on SQL UPDATE statements but not
        always on session.merge(). We set last_update explicitly to guarantee
        the timestamp is always current.
        """
        if hasattr(entity, "last_update"):
            entity.last_update = datetime.now(timezone.utc).replace(tzinfo=None)
        merged = self._session.merge(entity)
        self._session.flush()
        return merged

    # ── Delete ─────────────────────────────────────────────────────────────────
    def delete(self, entity: T) -> None:
        """Remove an entity from the database."""
        self._session.delete(entity)
        self._session.flush()

    # ── Count (utility) ────────────────────────────────────────────────────────
    def count(self) -> int:
        """Return the total number of rows for this model."""
        stmt = select(func.count()).select_from(self._model)
        return self._session.execute(stmt).scalar_one()
