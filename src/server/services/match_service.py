"""Business operations for the Match domain."""

from __future__ import annotations

from typing import Any

from src.domain.models import Match
from src.server.converters import match_to_dto, to_dicts
from src.server.errors import NotFoundError, ValidationError
from src.server.services.base import BaseService
from src.server.validation import (
    optional_int,
    optional_number,
    parse_datetime,
)

_ROLES = (
    ("blue", "blue_fighter_id"),
    ("red", "red_fighter_id"),
    ("winner", "winner_id"),
)


class MatchService(BaseService):
    """CRUD and searches for matches."""

    # -- CRUD ----------------------------------------------------------

    def list_all(self) -> list[dict[str, Any]]:
        with self._uow() as uow:
            return to_dicts(uow.matches.get_all(), match_to_dto)

    def get_by_id(self, match_id: int) -> dict[str, Any] | None:
        with self._uow() as uow:
            match = uow.matches.get(match_id)
            if match is None:
                return None
            result = match_to_dto(match).to_dict()
            result["fighters_info"] = {
                role: self._fighter_name(uow, getattr(match, attr))
                for role, attr in _ROLES
            }
            return result

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        tournament_id = optional_int(payload, "tournament_id")
        if not tournament_id:
            raise ValidationError("tournament_id is required.")
        with self._uow() as uow:
            match = Match(
                tournament_id=tournament_id,
                category_id=optional_int(payload, "category_id"),
                blue_fighter_id=optional_int(payload, "blue_fighter_id"),
                red_fighter_id=optional_int(payload, "red_fighter_id"),
                winner_id=optional_int(payload, "winner_id"),
                round_number=optional_int(payload, "round_number"),
                duration_seconds=optional_number(payload, "duration_seconds"),
                win_method=payload.get("win_method"),
                scheduled_time=parse_datetime(
                    payload.get("scheduled_time"), "scheduled_time"
                ),
            )
            uow.matches.add(match)
            uow.commit()
            return match_to_dto(match).to_dict()

    def update(self, match_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        winner_id = optional_int(payload, "winner_id")
        duration = optional_number(payload, "duration_seconds")
        with self._uow() as uow:
            match = self._get_or_raise(uow, match_id)
            if "winner_id" in payload:
                match.winner_id = winner_id
            if "win_method" in payload:
                match.win_method = payload["win_method"] or None
            if "duration_seconds" in payload:
                match.duration_seconds = duration
            uow.matches.update(match)
            uow.commit()
            return match_to_dto(match).to_dict()

    def delete(self, match_id: int) -> None:
        with self._uow() as uow:
            match = self._get_or_raise(uow, match_id)
            uow.matches.delete(match)
            uow.commit()

    # -- Searches ------------------------------------------------------

    def get_by_tournament(self, tournament_id: int) -> list[dict[str, Any]]:
        with self._uow() as uow:
            found = uow.matches.get_by_tournament(tournament_id)
            return to_dicts(found, match_to_dto)

    def get_by_fighter(self, fighter_id: int) -> dict[str, Any]:
        with self._uow() as uow:
            return {
                "matches": to_dicts(
                    uow.matches.get_by_fighter(fighter_id), match_to_dto
                ),
                "total_wins": len(uow.matches.get_wins_by_fighter(fighter_id)),
            }

    def get_by_category(self, category_id: int) -> list[dict[str, Any]]:
        with self._uow() as uow:
            found = uow.matches.get_by_category(category_id)
            return to_dicts(found, match_to_dto)

    def get_by_round(
        self, tournament_id: int, round_number: int
    ) -> list[dict[str, Any]]:
        with self._uow() as uow:
            found = uow.matches.get_by_round(tournament_id, round_number)
            return to_dicts(found, match_to_dto)

    def get_wins_by_fighter(self, fighter_id: int) -> list[dict[str, Any]]:
        with self._uow() as uow:
            found = uow.matches.get_wins_by_fighter(fighter_id)
            return to_dicts(found, match_to_dto)

    # -- Internals -----------------------------------------------------

    @staticmethod
    def _get_or_raise(uow, match_id: int) -> Match:
        match = uow.matches.get(match_id)
        if match is None:
            raise NotFoundError(f"Match with id={match_id} not found.")
        return match

    @staticmethod
    def _fighter_name(uow, fighter_id: int | None) -> str | None:
        if not fighter_id:
            return None
        fighter = uow.fighters.get(fighter_id)
        if fighter is None:
            return "?"
        return f"{fighter.first_name} {fighter.last_name}"
