"""
services/match_service.py — business operations for the Match domain.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.domain.models import Match
from src.domain.repositories import UnitOfWork
from src.server.dto import MatchDTO


class MatchService:
    """Stateless service; each method opens its own UnitOfWork."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    # ── CRUD ───────────────────────────────────────────────────────────────────

    def list_all(self) -> list[dict[str, Any]]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            return [self._to_dto(m).to_dict() for m in uow.matches.get_all()]

    def get_by_id(self, match_id: int) -> dict[str, Any] | None:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            m = uow.matches.get(match_id)
            if m is None:
                return None
            result = self._to_dto(m).to_dict()
            # Enrich with fighter names for display
            fighters_info = {}
            for role, fid in [
                ("blue", m.blue_fighter_id),
                ("red", m.red_fighter_id),
                ("winner", m.winner_id),
            ]:
                if fid:
                    f = uow.fighters.get(fid)
                    fighters_info[role] = (
                        f"{f.first_name} {f.last_name}" if f else "?"
                    )
                else:
                    fighters_info[role] = None
            result["fighters_info"] = fighters_info
            return result

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        tournament_id = payload.get("tournament_id")
        if not tournament_id:
            raise ValueError("tournament_id is required.")

        scheduled_time = None
        if payload.get("scheduled_time"):
            try:
                scheduled_time = datetime.strptime(
                    payload["scheduled_time"], "%Y-%m-%d %H:%M"
                )
            except ValueError:
                pass

        with UnitOfWork(session_factory=self._session_factory) as uow:
            m = Match(
                tournament_id=tournament_id,
                category_id=payload.get("category_id"),
                blue_fighter_id=payload.get("blue_fighter_id"),
                red_fighter_id=payload.get("red_fighter_id"),
                winner_id=payload.get("winner_id"),
                round_number=payload.get("round_number"),
                duration_seconds=payload.get("duration_seconds"),
                win_method=payload.get("win_method"),
                scheduled_time=scheduled_time,
            )
            uow.matches.add(m)
            uow.commit()
            return self._to_dto(m).to_dict()

    def update(self, match_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            m = uow.matches.get(match_id)
            if m is None:
                raise ValueError(f"Match with id={match_id} not found.")
            if "winner_id" in payload:
                m.winner_id = payload["winner_id"]
            if "win_method" in payload:
                m.win_method = payload["win_method"] or None
            if "duration_seconds" in payload:
                m.duration_seconds = payload["duration_seconds"]
            uow.matches.update(m)
            uow.commit()
            return self._to_dto(m).to_dict()

    def delete(self, match_id: int) -> None:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            m = uow.matches.get(match_id)
            if m is None:
                raise ValueError(f"Match with id={match_id} not found.")
            uow.matches.delete(m)
            uow.commit()

    # ── Searches ───────────────────────────────────────────────────────────────

    def get_by_tournament(self, tournament_id: int) -> list[dict[str, Any]]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            return [
                self._to_dto(m).to_dict()
                for m in uow.matches.get_by_tournament(tournament_id)
            ]

    def get_by_fighter(self, fighter_id: int) -> dict[str, Any]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            all_matches = uow.matches.get_by_fighter(fighter_id)
            wins = uow.matches.get_wins_by_fighter(fighter_id)
            return {
                "matches": [self._to_dto(m).to_dict() for m in all_matches],
                "total_wins": len(wins),
            }

    def get_by_category(self, category_id: int) -> list[dict[str, Any]]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            return [
                self._to_dto(m).to_dict()
                for m in uow.matches.get_by_category(category_id)
            ]

    def get_by_round(
        self, tournament_id: int, round_number: int
    ) -> list[dict[str, Any]]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            return [
                self._to_dto(m).to_dict()
                for m in uow.matches.get_by_round(tournament_id, round_number)
            ]

    def get_wins_by_fighter(self, fighter_id: int) -> list[dict[str, Any]]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            return [
                self._to_dto(m).to_dict()
                for m in uow.matches.get_wins_by_fighter(fighter_id)
            ]

    # ── Converters ─────────────────────────────────────────────────────────────

    @staticmethod
    def _to_dto(m: Match) -> MatchDTO:
        return MatchDTO(
            match_id=m.match_id,
            tournament_id=m.tournament_id,
            category_id=m.category_id,
            blue_fighter_id=m.blue_fighter_id,
            red_fighter_id=m.red_fighter_id,
            winner_id=m.winner_id,
            round_number=m.round_number,
            duration_seconds=m.duration_seconds,
            win_method=m.win_method,
            scheduled_time=m.scheduled_time.isoformat() if m.scheduled_time else None,
        )
