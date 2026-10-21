"""Business operations for fighter/category/tournament registrations."""

from __future__ import annotations

from typing import Any

from src.domain.models import FighterCategoryRegistration
from src.server.converters import registration_to_dto, to_dicts
from src.server.errors import ConflictError, NotFoundError
from src.server.services.base import BaseService
from src.server.validation import optional_number, require_int

_KEY_FIELDS = ("fighter_id", "category_id", "tournament_id")


class RegistrationService(BaseService):
    """N:M registration with attributes (weight, approval)."""

    # -- Read ----------------------------------------------------------

    def list_all(self) -> list[dict[str, Any]]:
        with self._uow() as uow:
            return to_dicts(uow.registrations.get_all(), registration_to_dto)

    def get(
        self, fighter_id: int, category_id: int, tournament_id: int
    ) -> dict[str, Any] | None:
        with self._uow() as uow:
            reg = uow.registrations.get(
                (fighter_id, category_id, tournament_id)
            )
            return registration_to_dto(reg).to_dict() if reg else None

    def list_by_tournament(self, tournament_id: int) -> list[dict[str, Any]]:
        with self._uow() as uow:
            found = uow.registrations.get_by_tournament(tournament_id)
            return to_dicts(found, registration_to_dto)

    def list_by_fighter(self, fighter_id: int) -> list[dict[str, Any]]:
        with self._uow() as uow:
            found = uow.registrations.get_by_fighter(fighter_id)
            return to_dicts(found, registration_to_dto)

    def list_pending_approvals(
        self, tournament_id: int
    ) -> list[dict[str, Any]]:
        with self._uow() as uow:
            found = uow.registrations.get_pending_approvals(tournament_id)
            return to_dicts(found, registration_to_dto)

    # -- Write ---------------------------------------------------------

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        key = self._key_from(payload)
        weight = optional_number(payload, "weight_in_weight_kg")
        with self._uow() as uow:
            if uow.registrations.get(key):
                raise ConflictError("Registration already exists.")
            reg = FighterCategoryRegistration(
                fighter_id=key[0],
                category_id=key[1],
                tournament_id=key[2],
                weight_in_weight_kg=weight,
                is_approved=bool(payload.get("is_approved", False)),
            )
            uow.registrations.add(reg)
            uow.commit()
            return registration_to_dto(reg).to_dict()

    def update(self, payload: dict[str, Any]) -> dict[str, Any]:
        key = self._key_from(payload)
        weight = optional_number(payload, "weight_in_weight_kg")
        with self._uow() as uow:
            reg = self._get_or_raise(uow, key)
            if "weight_in_weight_kg" in payload:
                reg.weight_in_weight_kg = weight
            if "is_approved" in payload:
                reg.is_approved = bool(payload["is_approved"])
            uow.registrations.update(reg)
            uow.commit()
            return registration_to_dto(reg).to_dict()

    def approve(
        self, fighter_id: int, category_id: int, tournament_id: int
    ) -> dict[str, Any]:
        with self._uow() as uow:
            try:
                reg = uow.fighters.approve_registration(
                    fighter_id, category_id, tournament_id
                )
            except ValueError as exc:
                raise NotFoundError(str(exc)) from exc
            uow.commit()
            return registration_to_dto(reg).to_dict()

    def delete(
        self, fighter_id: int, category_id: int, tournament_id: int
    ) -> None:
        with self._uow() as uow:
            reg = self._get_or_raise(
                uow, (fighter_id, category_id, tournament_id)
            )
            uow.registrations.delete(reg)
            uow.commit()

    # -- Internals -----------------------------------------------------

    @staticmethod
    def _key_from(payload: dict[str, Any]) -> tuple[int, int, int]:
        fighter_id, category_id, tournament_id = (
            require_int(payload, name) for name in _KEY_FIELDS
        )
        return fighter_id, category_id, tournament_id

    @staticmethod
    def _get_or_raise(
        uow, key: tuple[int, int, int]
    ) -> FighterCategoryRegistration:
        reg = uow.registrations.get(key)
        if reg is None:
            raise NotFoundError("Registration not found.")
        return reg
