"""TournamentRepository — domain operations for Tournament."""

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.models.tournament import Tournament
from src.domain.models.tatami import Tatami
from .base_repository import BaseRepository


class TournamentRepository(BaseRepository[Tournament]):

    def __init__(self, session: Session) -> None:
        super().__init__(session, Tournament)

    # ── Specific queries ─────────────────────────────────────────────────────

    def get_by_name(self, name: str) -> List[Tournament]:
        """Return tournaments whose name contains the string (any case)."""
        stmt = select(Tournament).where(Tournament.name.ilike(f"%{name}%"))
        return list(self._session.scalars(stmt).all())

    def get_by_location(self, location: str) -> List[Tournament]:
        """Return tournaments whose location contains the string (any case)."""
        stmt = select(Tournament).where(
            Tournament.location.ilike(f"%{location}%")
        )
        return list(self._session.scalars(stmt).all())

    def get_active_tournaments(self) -> List[Tournament]:
        """Return tournaments whose end_date is in the future (or not set)."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        stmt = select(Tournament).where(
            (Tournament.end_date >= now) | (Tournament.end_date.is_(None))
        )
        return list(self._session.scalars(stmt).all())

    def get_upcoming(self) -> List[Tournament]:
        """Return tournaments not started yet, ordered by start date."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        stmt = (
            select(Tournament)
            .where(Tournament.start_date > now)
            .order_by(Tournament.start_date)
        )
        return list(self._session.scalars(stmt).all())

    # ── Domain operations ────────────────────────────────────────────────────

    def add_tatami_to_tournament(
        self,
        tournament_id: int,
        name: str,
        mat_number: Optional[int] = None,
        area_size: Optional[float] = None,
        is_active: bool = True,
    ) -> Tatami:
        """Create a new tatami and attach it to a tournament.

        Raises ValueError if the tournament does not exist.
        """
        tournament = self.get(tournament_id)
        if tournament is None:
            raise ValueError(f"Tournament with id={tournament_id} not found.")
        tatami = Tatami(
            tournament_id=tournament_id,
            name=name,
            mat_number=mat_number,
            area_size=area_size,
            is_active=is_active,
        )
        self._session.add(tatami)
        self._session.flush()
        return tatami
