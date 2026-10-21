"""Business operations for the Fighter domain.

All methods accept and return plain dicts (no ORM object leaks out).
"""

from __future__ import annotations

from typing import Any

from src.domain.models import Fighter
from src.server.converters import (
    fighter_to_dto,
    medical_record_to_dto,
    registration_to_dto,
    to_dicts,
)
from src.server.errors import ConflictError, NotFoundError, ValidationError
from src.server.services.base import BaseService
from src.server.services.registration_service import RegistrationService
from src.server.validation import clean_str, parse_datetime

_UPDATABLE_TEXT_FIELDS = (
    "gender",
    "belt_level",
    "club_name",
    "country",
    "phone",
)
_MEDICAL_FIELDS = ("blood_type", "doctor_name", "conditions", "notes")


class FighterService(BaseService):
    """CRUD, searches and domain operations for fighters."""

    # -- CRUD ----------------------------------------------------------

    def list_all(self) -> list[dict[str, Any]]:
        with self._uow() as uow:
            return to_dicts(uow.fighters.get_all(), fighter_to_dto)

    def list_paginated(
        self, page: int = 1, page_size: int = 10
    ) -> dict[str, Any]:
        with self._uow() as uow:
            fighters = uow.fighters.get_paginated(
                page=page, page_size=page_size
            )
            return {
                "total": uow.fighters.count(),
                "page": page,
                "page_size": page_size,
                "items": to_dicts(fighters, fighter_to_dto),
            }

    def get_by_id(self, fighter_id: int) -> dict[str, Any] | None:
        with self._uow() as uow:
            fighter = uow.fighters.get(fighter_id)
            if fighter is None:
                return None
            result = fighter_to_dto(fighter).to_dict()
            record = fighter.medical_record
            result["medical_record"] = (
                medical_record_to_dto(record).to_dict() if record else None
            )
            result["registrations"] = to_dicts(
                uow.registrations.get_by_fighter(fighter_id),
                registration_to_dto,
            )
            result["total_matches"] = len(
                uow.matches.get_by_fighter(fighter_id)
            )
            result["total_wins"] = len(
                uow.matches.get_wins_by_fighter(fighter_id)
            )
            return result

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a new fighter from *payload* and return its DTO."""
        first_name = clean_str(payload.get("first_name"))
        last_name = clean_str(payload.get("last_name"))
        if not first_name or not last_name:
            raise ValidationError("first_name and last_name are required.")
        birth_date = parse_datetime(payload.get("birth_date"), "birth_date")
        email = clean_str(payload.get("email")) or None

        with self._uow() as uow:
            self._ensure_email_available(uow, email)
            fighter = Fighter(
                first_name=first_name,
                last_name=last_name,
                gender=payload.get("gender"),
                belt_level=payload.get("belt_level"),
                club_name=payload.get("club_name"),
                country=payload.get("country"),
                email=email,
                phone=payload.get("phone"),
                birth_date=birth_date,
            )
            uow.fighters.add(fighter)
            uow.commit()
            return fighter_to_dto(fighter).to_dict()

    def update(
        self, fighter_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        birth_date = parse_datetime(payload.get("birth_date"), "birth_date")
        with self._uow() as uow:
            fighter = self._get_or_raise(uow, fighter_id)
            for name in ("first_name", "last_name"):
                value = clean_str(payload.get(name))
                if value:
                    setattr(fighter, name, value)
            for name in _UPDATABLE_TEXT_FIELDS:
                if name in payload:
                    setattr(fighter, name, payload[name] or None)
            if "email" in payload:
                email = clean_str(payload["email"]) or None
                self._ensure_email_available(uow, email, fighter_id)
                fighter.email = email
            if "birth_date" in payload:
                fighter.birth_date = birth_date
            uow.fighters.update(fighter)
            uow.commit()
            return fighter_to_dto(fighter).to_dict()

    def delete(self, fighter_id: int) -> None:
        with self._uow() as uow:
            fighter = self._get_or_raise(uow, fighter_id)
            uow.fighters.delete(fighter)
            uow.commit()

    # -- Searches ------------------------------------------------------

    def search_by_last_name(self, last_name: str) -> list[dict[str, Any]]:
        with self._uow() as uow:
            found = uow.fighters.get_by_last_name(last_name)
            return to_dicts(found, fighter_to_dto)

    def search_by_belt_level(self, belt_level: str) -> list[dict[str, Any]]:
        with self._uow() as uow:
            found = uow.fighters.get_by_belt_level(belt_level)
            return to_dicts(found, fighter_to_dto)

    def search_by_country(self, country: str) -> list[dict[str, Any]]:
        with self._uow() as uow:
            found = uow.fighters.get_by_country(country)
            return to_dicts(found, fighter_to_dto)

    def search_by_email(self, email: str) -> dict[str, Any] | None:
        with self._uow() as uow:
            fighter = uow.fighters.get_by_email(email)
            return fighter_to_dto(fighter).to_dict() if fighter else None

    # -- Domain operations ---------------------------------------------

    def upsert_medical_record(
        self, fighter_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Create or update the medical record for a fighter."""
        with self._uow() as uow:
            fighter = self._get_or_raise(uow, fighter_id)
            record = fighter.medical_record
            if record:
                for name in _MEDICAL_FIELDS:
                    if name in payload:
                        setattr(record, name, payload[name] or None)
                uow.fighters.update(fighter)
            else:
                record = uow.fighters.add_medical_record(
                    fighter_id=fighter_id,
                    **{name: payload.get(name) for name in _MEDICAL_FIELDS},
                )
            uow.commit()
            return medical_record_to_dto(record).to_dict()

    def approve_registration(
        self, fighter_id: int, category_id: int, tournament_id: int
    ) -> dict[str, Any]:
        """Approve a registration (delegates to RegistrationService)."""
        return RegistrationService(self._session_factory).approve(
            fighter_id, category_id, tournament_id
        )

    # -- Internals -----------------------------------------------------

    @staticmethod
    def _get_or_raise(uow, fighter_id: int) -> Fighter:
        fighter = uow.fighters.get(fighter_id)
        if fighter is None:
            raise NotFoundError(f"Fighter with id={fighter_id} not found.")
        return fighter

    @staticmethod
    def _ensure_email_available(
        uow, email: str | None, own_id: int | None = None
    ) -> None:
        if not email:
            return
        existing = uow.fighters.get_by_email(email)
        if existing is not None and existing.fighter_id != own_id:
            raise ConflictError(
                f"A fighter with email '{email}' already exists."
            )
