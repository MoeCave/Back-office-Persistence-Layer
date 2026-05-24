"""FighterCategoryRegistration — N:M association between Fighter, Category, Tournament."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .fighter import Fighter
    from .category import Category
    from .tournament import Tournament


class FighterCategoryRegistration(Base):
    """Registration of a fighter in a specific category and tournament.

    Composite PK: (fighter_id, category_id, tournament_id).
    Carries its own attributes: weight at weigh-in and approval status.
    """

    __tablename__ = "fighter_category_registration"

    # ── Composite PK ──────────────────────────────────────────────────────────
    fighter_id: Mapped[int] = mapped_column(
        ForeignKey("fighter.fighter_id", ondelete="CASCADE"),
        primary_key=True,
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("category.category_id", ondelete="CASCADE"),
        primary_key=True,
    )
    tournament_id: Mapped[int] = mapped_column(
        ForeignKey("tournament.tournament_id", ondelete="CASCADE"),
        primary_key=True,
    )

    # ── Own attributes ─────────────────────────────────────────────────────────
    weight_in_weight_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    registration_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, server_default=func.now()
    )
    is_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_update: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, onupdate=func.now()
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    fighter: Mapped["Fighter"] = relationship(
        "Fighter", back_populates="registrations"
    )
    category: Mapped["Category"] = relationship(
        "Category", back_populates="registrations"
    )
    tournament: Mapped["Tournament"] = relationship(
        "Tournament", back_populates="registrations"
    )

    def __repr__(self) -> str:
        return (
            f"<Registration fighter={self.fighter_id} "
            f"category={self.category_id} "
            f"tournament={self.tournament_id}>"
        )
