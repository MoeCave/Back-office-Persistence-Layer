"""Conversion of ORM entities into DTOs (single source of truth).

Services call these functions so that no ORM object ever leaves the
server and every entity has exactly one serialisation rule.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, TypeVar

from src.domain.models import (
    Category,
    Fighter,
    FighterCategoryRegistration,
    Match,
    MedicalRecord,
    Tatami,
    Tournament,
)
from src.server.dto import (
    CategoryDTO,
    FighterDTO,
    MatchDTO,
    MedicalRecordDTO,
    RegistrationDTO,
    TatamiDTO,
    TournamentDTO,
    format_datetime,
)

T = TypeVar("T")


def to_dicts(
    items: Iterable[T], converter: Callable[[T], Any]
) -> list[dict[str, Any]]:
    """Convert every item with *converter* and return plain dicts."""
    return [converter(item).to_dict() for item in items]


def fighter_to_dto(fighter: Fighter) -> FighterDTO:
    return FighterDTO(
        fighter_id=fighter.fighter_id,
        first_name=fighter.first_name,
        last_name=fighter.last_name,
        gender=fighter.gender,
        belt_level=fighter.belt_level,
        club_name=fighter.club_name,
        country=fighter.country,
        email=fighter.email,
        phone=fighter.phone,
        birth_date=format_datetime(fighter.birth_date),
        created_at=format_datetime(fighter.created_at),
    )


def medical_record_to_dto(record: MedicalRecord) -> MedicalRecordDTO:
    return MedicalRecordDTO(
        medical_record_id=record.medical_record_id,
        fighter_id=record.fighter_id,
        blood_type=record.blood_type,
        notes=record.notes,
        conditions=record.conditions,
        doctor_name=record.doctor_name,
    )


def tournament_to_dto(tournament: Tournament) -> TournamentDTO:
    return TournamentDTO(
        tournament_id=tournament.tournament_id,
        name=tournament.name,
        location=tournament.location,
        start_date=format_datetime(tournament.start_date),
        end_date=format_datetime(tournament.end_date),
        max_fighters=tournament.max_fighters,
        created_at=format_datetime(tournament.created_at),
    )


def tatami_to_dto(tatami: Tatami) -> TatamiDTO:
    return TatamiDTO(
        tatami_id=tatami.tatami_id,
        tournament_id=tatami.tournament_id,
        name=tatami.name,
        mat_number=tatami.mat_number,
        area_size=tatami.area_size,
        is_active=tatami.is_active,
    )


def category_to_dto(category: Category) -> CategoryDTO:
    return CategoryDTO(
        category_id=category.category_id,
        name=category.name,
        belt_level=category.belt_level,
        weight_min_kg=category.weight_min_kg,
        weight_max_kg=category.weight_max_kg,
        gender=category.gender,
    )


def match_to_dto(match: Match) -> MatchDTO:
    return MatchDTO(
        match_id=match.match_id,
        tournament_id=match.tournament_id,
        category_id=match.category_id,
        blue_fighter_id=match.blue_fighter_id,
        red_fighter_id=match.red_fighter_id,
        winner_id=match.winner_id,
        round_number=match.round_number,
        duration_seconds=match.duration_seconds,
        win_method=match.win_method,
        scheduled_time=format_datetime(match.scheduled_time),
    )


def registration_to_dto(
    registration: FighterCategoryRegistration,
) -> RegistrationDTO:
    return RegistrationDTO(
        fighter_id=registration.fighter_id,
        category_id=registration.category_id,
        tournament_id=registration.tournament_id,
        weight_in_weight_kg=registration.weight_in_weight_kg,
        registration_date=format_datetime(registration.registration_date),
        is_approved=registration.is_approved,
        last_update=format_datetime(registration.last_update),
    )
