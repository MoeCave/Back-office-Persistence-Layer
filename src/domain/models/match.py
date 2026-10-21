"""Match model — a single bout within a tournament."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .tournament import Tournament
    from .category import Category
    from .fighter import Fighter


class Match(Base):
    """A single competitive match between two fighters."""

    __tablename__ = "match"

    match_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scheduled_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    round_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    win_method: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    last_update: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, onupdate=func.now()
    )

    # ── Foreign Keys ─────────────────────────────────────────────────────────
    tournament_id: Mapped[int] = mapped_column(
        ForeignKey("tournament.tournament_id", ondelete="CASCADE"),
        nullable=False,
    )
    category_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("category.category_id", ondelete="SET NULL"), nullable=True
    )
    blue_fighter_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("fighter.fighter_id", ondelete="SET NULL"), nullable=True
    )
    red_fighter_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("fighter.fighter_id", ondelete="SET NULL"), nullable=True
    )
    winner_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("fighter.fighter_id", ondelete="SET NULL"), nullable=True
    )

    # ── Relationships ────────────────────────────────────────────────────────
    tournament: Mapped["Tournament"] = relationship(
        "Tournament", back_populates="matches"
    )
    category: Mapped[Optional["Category"]] = relationship(
        "Category", back_populates="matches"
    )
    blue_fighter: Mapped[Optional["Fighter"]] = relationship(
        "Fighter",
        foreign_keys=[blue_fighter_id],
        back_populates="blue_matches",
    )
    red_fighter: Mapped[Optional["Fighter"]] = relationship(
        "Fighter",
        foreign_keys=[red_fighter_id],
        back_populates="red_matches",
    )
    winner: Mapped[Optional["Fighter"]] = relationship(
        "Fighter",
        foreign_keys=[winner_id],
        back_populates="won_matches",
    )

    def __repr__(self) -> str:
        return (
            f"<Match id={self.match_id} "
            f"tournament={self.tournament_id} "
            f"round={self.round_number}>"
        )
