"""
services/tournament_service.py — business operations for the Tournament domain.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.domain.models import Tournament, Tatami
from src.domain.repositories import UnitOfWork
from src.server.dto import TournamentDTO, TatamiDTO


class TournamentService:
    """Stateless service; each method opens its own UnitOfWork."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    # ── CRUD ───────────────────────────────────────────────────────────────────

    def list_all(self) -> list[dict[str, Any]]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            return [self._to_dto(t).to_dict() for t in uow.tournaments.get_all()]

    def get_by_id(self, tournament_id: int) -> dict[str, Any] | None:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            t = uow.tournaments.get(tournament_id)
            if t is None:
                return None
            result = self._to_dto(t).to_dict()
            result["tatamis"] = [self._tatami_to_dto(ta).to_dict() for ta in t.tatamis]
            matches = uow.matches.get_by_tournament(tournament_id)
            regs = uow.registrations.get_by_tournament(tournament_id)
            result["total_matches"] = len(matches)
            result["total_registrations"] = len(regs)
            result["pending_registrations"] = sum(
                1 for r in regs if not r.is_approved
            )
            return result

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = payload.get("name", "").strip()
        if not name:
            raise ValueError("name is required.")
        start_date = self._parse_date(payload.get("start_date"))
        end_date = self._parse_date(payload.get("end_date"))
        with UnitOfWork(session_factory=self._session_factory) as uow:
            t = Tournament(
                name=name,
                location=payload.get("location"),
                start_date=start_date,
                end_date=end_date,
                max_fighters=payload.get("max_fighters"),
            )
            uow.tournaments.add(t)
            uow.commit()
            return self._to_dto(t).to_dict()

    def update(self, tournament_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            t = uow.tournaments.get(tournament_id)
            if t is None:
                raise ValueError(f"Tournament with id={tournament_id} not found.")
            if "name" in payload and payload["name"]:
                t.name = payload["name"]
            if "location" in payload:
                t.location = payload["location"] or None
            if "max_fighters" in payload:
                t.max_fighters = payload["max_fighters"]
            uow.tournaments.update(t)
            uow.commit()
            return self._to_dto(t).to_dict()

    def delete(self, tournament_id: int) -> None:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            t = uow.tournaments.get(tournament_id)
            if t is None:
                raise ValueError(f"Tournament with id={tournament_id} not found.")
            uow.tournaments.delete(t)
            uow.commit()

    # ── Searches ───────────────────────────────────────────────────────────────

    def search_by_name(self, name: str) -> list[dict[str, Any]]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            return [
                self._to_dto(t).to_dict()
                for t in uow.tournaments.get_by_name(name)
            ]

    def search_by_location(self, location: str) -> list[dict[str, Any]]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            return [
                self._to_dto(t).to_dict()
                for t in uow.tournaments.get_by_location(location)
            ]

    def list_active(self) -> list[dict[str, Any]]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            return [
                self._to_dto(t).to_dict()
                for t in uow.tournaments.get_active_tournaments()
            ]

    def list_upcoming(self) -> list[dict[str, Any]]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            return [
                self._to_dto(t).to_dict()
                for t in uow.tournaments.get_upcoming()
            ]

    # ── Tatami management ──────────────────────────────────────────────────────

    def add_tatami(
        self, tournament_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        name = payload.get("name", "").strip()
        if not name:
            raise ValueError("Tatami name is required.")
        with UnitOfWork(session_factory=self._session_factory) as uow:
            tatami = uow.tournaments.add_tatami_to_tournament(
                tournament_id=tournament_id,
                name=name,
                mat_number=payload.get("mat_number"),
                area_size=payload.get("area_size"),
                is_active=payload.get("is_active", True),
            )
            uow.commit()
            return self._tatami_to_dto(tatami).to_dict()

    def list_tatamis(self, tournament_id: int) -> list[dict[str, Any]]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            t = uow.tournaments.get(tournament_id)
            if t is None:
                raise ValueError(f"Tournament with id={tournament_id} not found.")
            return [self._tatami_to_dto(ta).to_dict() for ta in t.tatamis]

    # ── Converters ─────────────────────────────────────────────────────────────

    @staticmethod
    def _to_dto(t: Tournament) -> TournamentDTO:
        return TournamentDTO(
            tournament_id=t.tournament_id,
            name=t.name,
            location=t.location,
            start_date=t.start_date.isoformat() if t.start_date else None,
            end_date=t.end_date.isoformat() if t.end_date else None,
            max_fighters=t.max_fighters,
            created_at=t.created_at.isoformat() if t.created_at else None,
        )

    @staticmethod
    def _tatami_to_dto(ta: Tatami) -> TatamiDTO:
        return TatamiDTO(
            tatami_id=ta.tatami_id,
            tournament_id=ta.tournament_id,
            name=ta.name,
            mat_number=ta.mat_number,
            area_size=ta.area_size,
            is_active=ta.is_active,
        )

    @staticmethod
    def _parse_date(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except (ValueError, TypeError):
            return None
