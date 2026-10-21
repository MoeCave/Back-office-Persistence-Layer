"""MatchRepository — domain operations for the Match model."""

from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.models.match import Match
from .base_repository import BaseRepository


class MatchRepository(BaseRepository[Match]):

    def __init__(self, session: Session) -> None:
        super().__init__(session, Match)

    def get_by_tournament(self, tournament_id: int) -> List[Match]:
        """Return the matches of a tournament, ordered by round and time."""
        stmt = (
            select(Match)
            .where(Match.tournament_id == tournament_id)
            .order_by(Match.round_number, Match.scheduled_time)
        )
        return list(self._session.scalars(stmt).all())

    def get_by_fighter(self, fighter_id: int) -> List[Match]:
        """Return all matches (as blue or red corner) for a fighter."""
        stmt = select(Match).where(
            (Match.blue_fighter_id == fighter_id)
            | (Match.red_fighter_id == fighter_id)
        )
        return list(self._session.scalars(stmt).all())

    def get_by_category(self, category_id: int) -> List[Match]:
        """Return all matches in a given category."""
        stmt = select(Match).where(Match.category_id == category_id)
        return list(self._session.scalars(stmt).all())

    def get_by_round(
        self, tournament_id: int, round_number: int
    ) -> List[Match]:
        """Return all matches for a specific round within a tournament."""
        stmt = select(Match).where(
            Match.tournament_id == tournament_id,
            Match.round_number == round_number,
        )
        return list(self._session.scalars(stmt).all())

    def get_wins_by_fighter(self, fighter_id: int) -> List[Match]:
        """Return all matches won by a fighter."""
        stmt = select(Match).where(Match.winner_id == fighter_id)
        return list(self._session.scalars(stmt).all())
