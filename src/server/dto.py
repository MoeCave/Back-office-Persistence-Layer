"""
dto.py — Data Transfer Objects for client/server communication.

These plain dataclasses decouple the wire format from SQLAlchemy models.
All serialisation (to/from dict) lives here so both client and server
can share the same schema without importing ORM internals.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Optional

# ── Helpers ──────────────────────────────────────────────────────────────────


def format_datetime(value: Optional[datetime]) -> Optional[str]:
    """Render a datetime as an ISO-8601 string, or ``None``."""
    return value.isoformat() if value else None


# ── DTOs ─────────────────────────────────────────────────────────────────────


@dataclass
class FighterDTO:
    fighter_id: Optional[int]
    first_name: str
    last_name: str
    gender: Optional[str] = None
    belt_level: Optional[str] = None
    club_name: Optional[str] = None
    country: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    birth_date: Optional[str] = None  # ISO-8601 string
    created_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FighterDTO":
        return cls(
            fighter_id=d.get("fighter_id"),
            first_name=d.get("first_name", ""),
            last_name=d.get("last_name", ""),
            gender=d.get("gender"),
            belt_level=d.get("belt_level"),
            club_name=d.get("club_name"),
            country=d.get("country"),
            email=d.get("email"),
            phone=d.get("phone"),
            birth_date=d.get("birth_date"),
            created_at=d.get("created_at"),
        )


@dataclass
class MedicalRecordDTO:
    medical_record_id: Optional[int]
    fighter_id: int
    blood_type: Optional[str] = None
    notes: Optional[str] = None
    conditions: Optional[str] = None
    doctor_name: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "MedicalRecordDTO":
        return cls(
            medical_record_id=d.get("medical_record_id"),
            fighter_id=d.get("fighter_id", 0),
            blood_type=d.get("blood_type"),
            notes=d.get("notes"),
            conditions=d.get("conditions"),
            doctor_name=d.get("doctor_name"),
        )


@dataclass
class TournamentDTO:
    tournament_id: Optional[int]
    name: str
    location: Optional[str] = None
    start_date: Optional[str] = None  # ISO-8601
    end_date: Optional[str] = None  # ISO-8601
    max_fighters: Optional[int] = None
    created_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TournamentDTO":
        return cls(
            tournament_id=d.get("tournament_id"),
            name=d.get("name", ""),
            location=d.get("location"),
            start_date=d.get("start_date"),
            end_date=d.get("end_date"),
            max_fighters=d.get("max_fighters"),
            created_at=d.get("created_at"),
        )


@dataclass
class TatamiDTO:
    tatami_id: Optional[int]
    tournament_id: int
    name: str
    mat_number: Optional[int] = None
    area_size: Optional[float] = None
    is_active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TatamiDTO":
        return cls(
            tatami_id=d.get("tatami_id"),
            tournament_id=d.get("tournament_id", 0),
            name=d.get("name", ""),
            mat_number=d.get("mat_number"),
            area_size=d.get("area_size"),
            is_active=d.get("is_active", True),
        )


@dataclass
class CategoryDTO:
    category_id: Optional[int]
    name: str
    belt_level: Optional[str] = None
    weight_min_kg: Optional[float] = None
    weight_max_kg: Optional[float] = None
    gender: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CategoryDTO":
        return cls(
            category_id=d.get("category_id"),
            name=d.get("name", ""),
            belt_level=d.get("belt_level"),
            weight_min_kg=d.get("weight_min_kg"),
            weight_max_kg=d.get("weight_max_kg"),
            gender=d.get("gender"),
        )


@dataclass
class MatchDTO:
    match_id: Optional[int]
    tournament_id: int
    category_id: Optional[int] = None
    blue_fighter_id: Optional[int] = None
    red_fighter_id: Optional[int] = None
    winner_id: Optional[int] = None
    round_number: Optional[int] = None
    duration_seconds: Optional[float] = None
    win_method: Optional[str] = None
    scheduled_time: Optional[str] = None  # ISO-8601

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "MatchDTO":
        return cls(
            match_id=d.get("match_id"),
            tournament_id=d.get("tournament_id", 0),
            category_id=d.get("category_id"),
            blue_fighter_id=d.get("blue_fighter_id"),
            red_fighter_id=d.get("red_fighter_id"),
            winner_id=d.get("winner_id"),
            round_number=d.get("round_number"),
            duration_seconds=d.get("duration_seconds"),
            win_method=d.get("win_method"),
            scheduled_time=d.get("scheduled_time"),
        )


@dataclass
class RegistrationDTO:
    fighter_id: int
    category_id: int
    tournament_id: int
    weight_in_weight_kg: Optional[float] = None
    registration_date: Optional[str] = None  # ISO-8601
    is_approved: bool = False
    last_update: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RegistrationDTO":
        return cls(
            fighter_id=d.get("fighter_id", 0),
            category_id=d.get("category_id", 0),
            tournament_id=d.get("tournament_id", 0),
            weight_in_weight_kg=d.get("weight_in_weight_kg"),
            registration_date=d.get("registration_date"),
            is_approved=d.get("is_approved", False),
            last_update=d.get("last_update"),
        )
