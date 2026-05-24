"""Fighter model — aggregate root for a competition participant."""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .medical_record import MedicalRecord
    from .fighter_category_registration import FighterCategoryRegistration
    from .match import Match


class Fighter(Base):
    """Represents a fighter / competitor.

    Aggregate root: owns MedicalRecord (1:1), FighterCategoryRegistration (1:N),
    and participates in Match records as blue, red, or winner.
    """

    __tablename__ = "fighter"

    fighter_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    birth_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    belt_level: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    club_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    last_update: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, onupdate=func.now()
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    medical_record: Mapped[Optional["MedicalRecord"]] = relationship(
        "MedicalRecord",
        back_populates="fighter",
        uselist=False,
        cascade="all, delete-orphan",
    )

    registrations: Mapped[List["FighterCategoryRegistration"]] = relationship(
        "FighterCategoryRegistration",
        back_populates="fighter",
        cascade="all, delete-orphan",
    )

    blue_matches: Mapped[List["Match"]] = relationship(
        "Match",
        foreign_keys="Match.blue_fighter_id",
        back_populates="blue_fighter",
    )

    red_matches: Mapped[List["Match"]] = relationship(
        "Match",
        foreign_keys="Match.red_fighter_id",
        back_populates="red_fighter",
    )

    won_matches: Mapped[List["Match"]] = relationship(
        "Match",
        foreign_keys="Match.winner_id",
        back_populates="winner",
    )

    def __repr__(self) -> str:
        return (
            f"<Fighter id={self.fighter_id} "
            f"name='{self.first_name} {self.last_name}'>"
        )
