"""Tournament model — aggregate root for a competition event."""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .tatami import Tatami
    from .match import Match
    from .fighter_category_registration import FighterCategoryRegistration


class Tournament(Base):
    """A tournament / competition event.

    Aggregate root: owns Tatami (1:N), Match (1:N),
    and FighterCategoryRegistration (1:N).
    """

    __tablename__ = "tournament"

    tournament_id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    start_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    end_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    max_fighters: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    last_update: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, onupdate=func.now()
    )

    # ── Relationships ────────────────────────────────────────────────────────
    tatamis: Mapped[List["Tatami"]] = relationship(
        "Tatami",
        back_populates="tournament",
        cascade="all, delete-orphan",
    )

    matches: Mapped[List["Match"]] = relationship(
        "Match",
        back_populates="tournament",
        cascade="all, delete-orphan",
    )

    registrations: Mapped[List["FighterCategoryRegistration"]] = relationship(
        "FighterCategoryRegistration",
        back_populates="tournament",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Tournament id={self.tournament_id} name='{self.name}'>"
