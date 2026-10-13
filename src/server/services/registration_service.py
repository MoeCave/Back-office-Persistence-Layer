"""
services/registration_service.py — business operations for the
FighterCategoryRegistration N:M+attrs domain.
"""

from __future__ import annotations

from typing import Any

from src.domain.models import FighterCategoryRegistration
from src.domain.repositories import UnitOfWork
from src.server.dto import RegistrationDTO


class RegistrationService:
    """Stateless service; each method opens its own UnitOfWork."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    # ── Read ───────────────────────────────────────────────────────────────────

    def list_all(self) -> list[dict[str, Any]]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            return [
                self._to_dto(r).to_dict()
                for r in uow.registrations.get_all()
            ]

    def get(
        self, fighter_id: int, category_id: int, tournament_id: int
    ) -> dict[str, Any] | None:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            reg = uow.registrations.get((fighter_id, category_id, tournament_id))
            return self._to_dto(reg).to_dict() if reg else None

    def list_by_tournament(self, tournament_id: int) -> list[dict[str, Any]]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            return [
                self._to_dto(r).to_dict()
                for r in uow.registrations.get_by_tournament(tournament_id)
            ]

    def list_by_fighter(self, fighter_id: int) -> list[dict[str, Any]]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            return [
                self._to_dto(r).to_dict()
                for r in uow.registrations.get_by_fighter(fighter_id)
            ]

    def list_pending_approvals(self, tournament_id: int) -> list[dict[str, Any]]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            return [
                self._to_dto(r).to_dict()
                for r in uow.registrations.get_pending_approvals(tournament_id)
            ]

    # ── Write ──────────────────────────────────────────────────────────────────

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        fighter_id = payload.get("fighter_id")
        category_id = payload.get("category_id")
        tournament_id = payload.get("tournament_id")
        if None in (fighter_id, category_id, tournament_id):
            raise ValueError(
                "fighter_id, category_id, and tournament_id are required."
            )
        with UnitOfWork(session_factory=self._session_factory) as uow:
            existing = uow.registrations.get(
                (fighter_id, category_id, tournament_id)
            )
            if existing:
                raise ValueError("Registration already exists.")
            reg = FighterCategoryRegistration(
                fighter_id=fighter_id,
                category_id=category_id,
                tournament_id=tournament_id,
                weight_in_weight_kg=payload.get("weight_in_weight_kg"),
                is_approved=payload.get("is_approved", False),
            )
            uow.registrations.add(reg)
            uow.commit()
            return self._to_dto(reg).to_dict()

    def update(self, payload: dict[str, Any]) -> dict[str, Any]:
        fighter_id = payload.get("fighter_id")
        category_id = payload.get("category_id")
        tournament_id = payload.get("tournament_id")
        if None in (fighter_id, category_id, tournament_id):
            raise ValueError(
                "fighter_id, category_id, and tournament_id are required."
            )
        with UnitOfWork(session_factory=self._session_factory) as uow:
            reg = uow.registrations.get((fighter_id, category_id, tournament_id))
            if reg is None:
                raise ValueError("Registration not found.")
            if "weight_in_weight_kg" in payload:
                reg.weight_in_weight_kg = payload["weight_in_weight_kg"]
            if "is_approved" in payload:
                reg.is_approved = bool(payload["is_approved"])
            uow.registrations.update(reg)
            uow.commit()
            return self._to_dto(reg).to_dict()

    def approve(
        self, fighter_id: int, category_id: int, tournament_id: int
    ) -> dict[str, Any]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            reg = uow.fighters.approve_registration(
                fighter_id, category_id, tournament_id
            )
            uow.commit()
            return self._to_dto(reg).to_dict()

    def delete(
        self, fighter_id: int, category_id: int, tournament_id: int
    ) -> None:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            reg = uow.registrations.get((fighter_id, category_id, tournament_id))
            if reg is None:
                raise ValueError("Registration not found.")
            uow.registrations.delete(reg)
            uow.commit()

    # ── Converters ─────────────────────────────────────────────────────────────

    @staticmethod
    def _to_dto(r: FighterCategoryRegistration) -> RegistrationDTO:
        return RegistrationDTO(
            fighter_id=r.fighter_id,
            category_id=r.category_id,
            tournament_id=r.tournament_id,
            weight_in_weight_kg=r.weight_in_weight_kg,
            registration_date=(
                r.registration_date.isoformat() if r.registration_date else None
            ),
            is_approved=r.is_approved,
            last_update=r.last_update.isoformat() if r.last_update else None,
        )
