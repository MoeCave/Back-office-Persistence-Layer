"""CategoryRepository — domain operations for the Category model."""

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.models.category import Category
from .base_repository import BaseRepository


class CategoryRepository(BaseRepository[Category]):

    def __init__(self, session: Session) -> None:
        super().__init__(session, Category)

    def get_by_name(self, name: str) -> List[Category]:
        """Return categories whose name matches (case-insensitive partial)."""
        stmt = select(Category).where(Category.name.ilike(f"%{name}%"))
        return list(self._session.scalars(stmt).all())

    def get_by_belt_level(self, belt_level: str) -> List[Category]:
        """Return all categories for a specific belt level."""
        stmt = select(Category).where(Category.belt_level == belt_level)
        return list(self._session.scalars(stmt).all())

    def get_by_gender(self, gender: str) -> List[Category]:
        """Return all categories for a specific gender."""
        stmt = select(Category).where(Category.gender == gender)
        return list(self._session.scalars(stmt).all())

    def get_by_weight_range(
        self,
        min_kg: Optional[float] = None,
        max_kg: Optional[float] = None,
    ) -> List[Category]:
        """Return categories that fall within an optional weight range."""
        stmt = select(Category)
        if min_kg is not None:
            stmt = stmt.where(Category.weight_min_kg >= min_kg)
        if max_kg is not None:
            stmt = stmt.where(Category.weight_max_kg <= max_kg)
        return list(self._session.scalars(stmt).all())
