"""Conversión de entidades ORM de SQLAlchemy a DTOs tipados (SSOT).

Los servicios invocan estas funciones para garantizar que ningún objeto ORM
ni sesión escape fuera del servidor. Cada entidad cuenta con una regla única
y determinista de serialización hacia diccionarios planos JSON.

Convención: una función ``<entidad>_to_dto`` por modelo. Todas son puras
(no tocan la sesión salvo para leer atributos ya cargados), por lo que deben
llamarse DENTRO del bloque ``with uow`` mientras la sesión sigue abierta.
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

# Tipo genérico de la entidad ORM que se convierte en ``to_dicts``.
T = TypeVar("T")


def to_dicts(
    items: Iterable[T], converter: Callable[[T], Any]
) -> list[dict[str, Any]]:
    """Convert every item with *converter* and return plain dicts.

    Args:
        items: Entidades ORM (lista, resultado de consulta, relación...).
        converter: Función ``*_to_dto`` que devuelve un DTO con ``to_dict``.

    Returns:
        Lista de diccionarios JSON-serializables, en el mismo orden.
    """
    return [converter(item).to_dict() for item in items]


def fighter_to_dto(fighter: Fighter) -> FighterDTO:
    """Convierte un ``Fighter`` en ``FighterDTO``.

    No incluye relaciones (ficha médica, inscripciones, combates): esas se
    añaden explícitamente en ``FighterService.get_by_id``. Las fechas se
    serializan a ISO-8601 mediante ``format_datetime``.
    """
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
    """Convierte un ``MedicalRecord`` (relación 1:1 con Fighter) en DTO."""
    return MedicalRecordDTO(
        medical_record_id=record.medical_record_id,
        fighter_id=record.fighter_id,
        blood_type=record.blood_type,
        notes=record.notes,
        conditions=record.conditions,
        doctor_name=record.doctor_name,
    )


def tournament_to_dto(tournament: Tournament) -> TournamentDTO:
    """Convierte un ``Tournament`` en ``TournamentDTO`` (sin tatamis)."""
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
    """Convierte un ``Tatami`` (relación 1:N con Tournament) en DTO."""
    return TatamiDTO(
        tatami_id=tatami.tatami_id,
        tournament_id=tatami.tournament_id,
        name=tatami.name,
        mat_number=tatami.mat_number,
        area_size=tatami.area_size,
        is_active=tatami.is_active,
    )


def category_to_dto(category: Category) -> CategoryDTO:
    """Convierte una ``Category`` en ``CategoryDTO``.

    Los contadores (``total_registrations``, ``total_matches``) los añade
    ``CategoryService.get_by_id``; este convertidor no los calcula.
    """
    return CategoryDTO(
        category_id=category.category_id,
        name=category.name,
        belt_level=category.belt_level,
        weight_min_kg=category.weight_min_kg,
        weight_max_kg=category.weight_max_kg,
        gender=category.gender,
    )


def match_to_dto(match: Match) -> MatchDTO:
    """Convierte un ``Match`` en ``MatchDTO``.

    Solo expone los IDs de esquina azul, roja y ganador; los nombres se
    resuelven aparte en ``MatchService.get_by_id`` (``fighters_info``).
    """
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
    """Convierte una inscripción N:M con atributos en ``RegistrationDTO``.

    La clave compuesta (fighter_id, category_id, tournament_id) viaja en el
    DTO, de modo que el cliente puede identificar la fila sin ID propio.
    """
    return RegistrationDTO(
        fighter_id=registration.fighter_id,
        category_id=registration.category_id,
        tournament_id=registration.tournament_id,
        weight_in_weight_kg=registration.weight_in_weight_kg,
        registration_date=format_datetime(registration.registration_date),
        is_approved=registration.is_approved,
        last_update=format_datetime(registration.last_update),
    )