"""Business operations for the Tournament domain."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.domain.models import Tournament
from src.server.converters import (
    tatami_to_dto,
    to_dicts,
    tournament_to_dto,
)
from src.server.errors import NotFoundError, ValidationError
from src.server.services.base import BaseService
from src.server.validation import (
    clean_str,
    optional_int,
    optional_number,
    parse_datetime,
)


class TournamentService(BaseService):
    """CRUD, searches and tatami management for tournaments."""

    # -- CRUD ----------------------------------------------------------

    def list_all(self) -> list[dict[str, Any]]:
        with self._uow() as uow:
            return to_dicts(uow.tournaments.get_all(), tournament_to_dto)

    def get_by_id(self, tournament_id: int) -> dict[str, Any] | None:
        with self._uow() as uow:
            tournament = uow.tournaments.get(tournament_id)
            if tournament is None:
                return None
            result = tournament_to_dto(tournament).to_dict()
            result["tatamis"] = to_dicts(tournament.tatamis, tatami_to_dto)
            registrations = uow.registrations.get_by_tournament(tournament_id)
            result["total_matches"] = len(
                uow.matches.get_by_tournament(tournament_id)
            )
            result["total_registrations"] = len(registrations)
            result["pending_registrations"] = sum(
                1 for reg in registrations if not reg.is_approved
            )
            return result

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = clean_str(payload.get("name"))
        if not name:
            raise ValidationError("name is required.")
        start_date = parse_datetime(payload.get("start_date"), "start_date")
        end_date = parse_datetime(payload.get("end_date"), "end_date")
        self._check_date_order(start_date, end_date)
        max_fighters = optional_int(payload, "max_fighters")
        with self._uow() as uow:
            tournament = Tournament(
                name=name,
                location=payload.get("location"),
                start_date=start_date,
                end_date=end_date,
                max_fighters=max_fighters,
            )
            uow.tournaments.add(tournament)
            uow.commit()
            return tournament_to_dto(tournament).to_dict()

    def update(
        self, tournament_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        start_date = parse_datetime(payload.get("start_date"), "start_date")
        end_date = parse_datetime(payload.get("end_date"), "end_date")
        max_fighters = optional_int(payload, "max_fighters")
        with self._uow() as uow:
            tournament = self._get_or_raise(uow, tournament_id)
            name = clean_str(payload.get("name"))
            if name:
                tournament.name = name
            if "location" in payload:
                tournament.location = payload["location"] or None
            if "max_fighters" in payload:
                tournament.max_fighters = max_fighters
            if "start_date" in payload:
                tournament.start_date = start_date
            if "end_date" in payload:
                tournament.end_date = end_date
            self._check_date_order(tournament.start_date, tournament.end_date)
            uow.tournaments.update(tournament)
            uow.commit()
            return tournament_to_dto(tournament).to_dict()

    def delete(self, tournament_id: int) -> None:
        with self._uow() as uow:
            tournament = self._get_or_raise(uow, tournament_id)
            uow.tournaments.delete(tournament)
            uow.commit()

    # -- Searches ------------------------------------------------------

    def search_by_name(self, name: str) -> list[dict[str, Any]]:
        with self._uow() as uow:
            found = uow.tournaments.get_by_name(name)
            return to_dicts(found, tournament_to_dto)

    def search_by_location(self, location: str) -> list[dict[str, Any]]:
        with self._uow() as uow:
            found = uow.tournaments.get_by_location(location)
            return to_dicts(found, tournament_to_dto)

    def list_active(self) -> list[dict[str, Any]]:
        with self._uow() as uow:
            found = uow.tournaments.get_active_tournaments()
            return to_dicts(found, tournament_to_dto)

    def list_upcoming(self) -> list[dict[str, Any]]:
        with self._uow() as uow:
            found = uow.tournaments.get_upcoming()
            return to_dicts(found, tournament_to_dto)

    # -- Tatami management ---------------------------------------------

    def add_tatami(
        self, tournament_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        name = clean_str(payload.get("name"))
        if not name:
            raise ValidationError("Tatami name is required.")
        mat_number = optional_int(payload, "mat_number")
        area_size = optional_number(payload, "area_size")
        with self._uow() as uow:
            self._get_or_raise(uow, tournament_id)
            tatami = uow.tournaments.add_tatami_to_tournament(
                tournament_id=tournament_id,
                name=name,
                mat_number=mat_number,
                area_size=area_size,
                is_active=bool(payload.get("is_active", True)),
            )
            uow.commit()
            return tatami_to_dto(tatami).to_dict()

    def list_tatamis(self, tournament_id: int) -> list[dict[str, Any]]:
        with self._uow() as uow:
            tournament = self._get_or_raise(uow, tournament_id)
            return to_dicts(tournament.tatamis, tatami_to_dto)

    # -- Internals -----------------------------------------------------

    @staticmethod
    def _get_or_raise(uow, tournament_id: int) -> Tournament:
        tournament = uow.tournaments.get(tournament_id)
        if tournament is None:
            raise NotFoundError(
                f"Tournament with id={tournament_id} not found."
            )
        return tournament

    @staticmethod
    def _check_date_order(
        start: datetime | None, end: datetime | None
    ) -> None:
        if start and end and end < start:
            raise ValidationError("end_date must not be before start_date.")
