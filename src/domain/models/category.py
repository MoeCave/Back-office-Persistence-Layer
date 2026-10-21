"""Category model — defines a competition division by belt and weight."""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .fighter_category_registration import FighterCategoryRegistration
    from .match import Match


class Category(Base):
    """A competition category (e.g. Blue belt, -70 kg, Male)."""

    __tablename__ = "category"

    category_id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    belt_level: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )
    weight_min_kg: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    weight_max_kg: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    gender: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    last_update: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, onupdate=func.now()
    )

    # ── Relationships ────────────────────────────────────────────────────────
    registrations: Mapped[List["FighterCategoryRegistration"]] = relationship(
        "FighterCategoryRegistration",
        back_populates="category",
        cascade="all, delete-orphan",
    )

    matches: Mapped[List["Match"]] = relationship(
        "Match",
        back_populates="category",
    )

    def __repr__(self) -> str:
        return f"<Category id={self.category_id} name='{self.name}'>"
