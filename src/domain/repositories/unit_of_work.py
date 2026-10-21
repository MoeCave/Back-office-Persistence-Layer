"""Unit of Work — one database session shared by all repositories."""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.domain.db import Session as DefaultSession
from .fighter_repository import FighterRepository
from .tournament_repository import TournamentRepository
from .category_repository import CategoryRepository
from .match_repository import MatchRepository
from .registration_repository import RegistrationRepository


class UnitOfWork:
    """Wraps a database session and exposes one repository per aggregate root.

    Usage:
        with UnitOfWork() as uow:
            uow.fighters.add(fighter)
            uow.commit()

    The session_factory parameter lets tests inject an in-memory session:
        with UnitOfWork(session_factory=TestSession) as uow:
            ...
    """

    def __init__(self, session_factory=None) -> None:
        self._session_factory = session_factory or DefaultSession

    def __enter__(self) -> "UnitOfWork":
        self._session: Session = self._session_factory()
        self.fighters = FighterRepository(self._session)
        self.tournaments = TournamentRepository(self._session)
        self.categories = CategoryRepository(self._session)
        self.matches = MatchRepository(self._session)
        self.registrations = RegistrationRepository(self._session)
        return self

    def commit(self) -> None:
        """Commit all pending changes to the database."""
        self._session.commit()

    def rollback(self) -> None:
        """Discard all pending changes."""
        self._session.rollback()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None:
            self.rollback()
        self._session.close()
        return False  # do not suppress exceptions
