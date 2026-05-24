"""MedicalRecord model — 1:1 extension of Fighter."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .fighter import Fighter


class MedicalRecord(Base):
    """Medical information attached to a single fighter (1:1, separate PK)."""

    __tablename__ = "medical_record"

    medical_record_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    blood_type: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    conditions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    doctor_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    fighter_id: Mapped[int] = mapped_column(
        ForeignKey("fighter.fighter_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    last_update: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, onupdate=func.now()
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    fighter: Mapped["Fighter"] = relationship(
        "Fighter", back_populates="medical_record"
    )

    def __repr__(self) -> str:
        return (
            f"<MedicalRecord id={self.medical_record_id} "
            f"fighter_id={self.fighter_id}>"
        )
