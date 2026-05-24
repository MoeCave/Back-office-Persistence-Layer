"""RegistrationRepository — CRUD for FighterCategoryRegistration."""

from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.models.fighter_category_registration import FighterCategoryRegistration
from .base_repository import BaseRepository


class RegistrationRepository(BaseRepository[FighterCategoryRegistration]):

    def __init__(self, session: Session) -> None:
        super().__init__(session, FighterCategoryRegistration)

    def get(  # type: ignore[override]
        self,
        pk: Tuple[int, int, int],
    ) -> Optional[FighterCategoryRegistration]:
        """Find a registration by its composite PK: (fighter_id, category_id, tournament_id)."""
        fighter_id, category_id, tournament_id = pk
        stmt = select(FighterCategoryRegistration).where(
            FighterCategoryRegistration.fighter_id == fighter_id,
            FighterCategoryRegistration.category_id == category_id,
            FighterCategoryRegistration.tournament_id == tournament_id,
        )
        return self._session.scalars(stmt).first()

    def get_by_tournament(self, tournament_id: int) -> List[FighterCategoryRegistration]:
        """Return all registrations for a given tournament."""
        stmt = select(FighterCategoryRegistration).where(
            FighterCategoryRegistration.tournament_id == tournament_id
        )
        return list(self._session.scalars(stmt).all())

    def get_by_fighter(self, fighter_id: int) -> List[FighterCategoryRegistration]:
        """Return all registrations for a given fighter."""
        stmt = select(FighterCategoryRegistration).where(
            FighterCategoryRegistration.fighter_id == fighter_id
        )
        return list(self._session.scalars(stmt).all())

    def get_pending_approvals(
        self, tournament_id: int
    ) -> List[FighterCategoryRegistration]:
        """Return unapproved registrations for a tournament."""
        stmt = select(FighterCategoryRegistration).where(
            FighterCategoryRegistration.tournament_id == tournament_id,
            FighterCategoryRegistration.is_approved.is_(False),
        )
        return list(self._session.scalars(stmt).all())
