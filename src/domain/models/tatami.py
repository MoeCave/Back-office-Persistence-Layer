"""Tatami model — a competition mat belonging to a tournament."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .tournament import Tournament


class Tatami(Base):
    """A tatami (mat) within a tournament venue."""

    __tablename__ = "tatami"

    tatami_id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    mat_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    area_size: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    tournament_id: Mapped[int] = mapped_column(
        ForeignKey("tournament.tournament_id", ondelete="CASCADE"),
        nullable=False,
    )
    last_update: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, onupdate=func.now()
    )

    # ── Relationships ────────────────────────────────────────────────────────
    tournament: Mapped["Tournament"] = relationship(
        "Tournament", back_populates="tatamis"
    )

    def __repr__(self) -> str:
        return f"<Tatami id={self.tatami_id} name='{self.name}'>"
