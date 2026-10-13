"""
services/fighter_service.py — business operations for the Fighter domain.

All methods accept/return plain dicts or DTOs (no ORM objects leak out).
"""

from __future__ import annotations

from typing import Any

from src.domain.models import Fighter, FighterCategoryRegistration
from src.domain.repositories import UnitOfWork
from src.server.dto import FighterDTO, MedicalRecordDTO, RegistrationDTO


class FighterService:
    """Stateless service; each method opens its own UnitOfWork."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    # ── CRUD ───────────────────────────────────────────────────────────────────

    def list_all(self) -> list[dict[str, Any]]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            fighters = uow.fighters.get_all()
            return [self._to_dto(f).to_dict() for f in fighters]

    def list_paginated(
        self, page: int = 1, page_size: int = 10
    ) -> dict[str, Any]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            total = uow.fighters.count()
            fighters = uow.fighters.get_paginated(page=page, page_size=page_size)
            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": [self._to_dto(f).to_dict() for f in fighters],
            }

    def get_by_id(self, fighter_id: int) -> dict[str, Any] | None:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            fighter = uow.fighters.get(fighter_id)
            if fighter is None:
                return None
            result = self._to_dto(fighter).to_dict()
            # Include related data
            result["medical_record"] = (
                MedicalRecordDTO(
                    medical_record_id=fighter.medical_record.medical_record_id,
                    fighter_id=fighter.medical_record.fighter_id,
                    blood_type=fighter.medical_record.blood_type,
                    notes=fighter.medical_record.notes,
                    conditions=fighter.medical_record.conditions,
                    doctor_name=fighter.medical_record.doctor_name,
                ).to_dict()
                if fighter.medical_record
                else None
            )
            regs = uow.registrations.get_by_fighter(fighter_id)
            result["registrations"] = [
                self._reg_to_dto(r).to_dict() for r in regs
            ]
            all_matches = uow.matches.get_by_fighter(fighter_id)
            wins = uow.matches.get_wins_by_fighter(fighter_id)
            result["total_matches"] = len(all_matches)
            result["total_wins"] = len(wins)
            return result

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a new fighter from *payload* and return its DTO."""
        from datetime import datetime

        first_name = payload.get("first_name", "").strip()
        last_name = payload.get("last_name", "").strip()
        if not first_name or not last_name:
            raise ValueError("first_name and last_name are required.")

        birth_date = None
        if payload.get("birth_date"):
            try:
                birth_date = datetime.strptime(payload["birth_date"], "%Y-%m-%d")
            except ValueError:
                pass  # silently ignore invalid dates

        with UnitOfWork(session_factory=self._session_factory) as uow:
            fighter = Fighter(
                first_name=first_name,
                last_name=last_name,
                gender=payload.get("gender"),
                belt_level=payload.get("belt_level"),
                club_name=payload.get("club_name"),
                country=payload.get("country"),
                email=payload.get("email"),
                phone=payload.get("phone"),
                birth_date=birth_date,
            )
            uow.fighters.add(fighter)
            uow.commit()
            return self._to_dto(fighter).to_dict()

    def update(self, fighter_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            fighter = uow.fighters.get(fighter_id)
            if fighter is None:
                raise ValueError(f"Fighter with id={fighter_id} not found.")
            if "first_name" in payload and payload["first_name"]:
                fighter.first_name = payload["first_name"]
            if "last_name" in payload and payload["last_name"]:
                fighter.last_name = payload["last_name"]
            for field in ("gender", "belt_level", "club_name", "country", "email", "phone"):
                if field in payload:
                    setattr(fighter, field, payload[field] or None)
            uow.fighters.update(fighter)
            uow.commit()
            return self._to_dto(fighter).to_dict()

    def delete(self, fighter_id: int) -> None:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            fighter = uow.fighters.get(fighter_id)
            if fighter is None:
                raise ValueError(f"Fighter with id={fighter_id} not found.")
            uow.fighters.delete(fighter)
            uow.commit()

    # ── Searches ───────────────────────────────────────────────────────────────

    def search_by_last_name(self, last_name: str) -> list[dict[str, Any]]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            return [
                self._to_dto(f).to_dict()
                for f in uow.fighters.get_by_last_name(last_name)
            ]

    def search_by_belt_level(self, belt_level: str) -> list[dict[str, Any]]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            return [
                self._to_dto(f).to_dict()
                for f in uow.fighters.get_by_belt_level(belt_level)
            ]

    def search_by_country(self, country: str) -> list[dict[str, Any]]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            return [
                self._to_dto(f).to_dict()
                for f in uow.fighters.get_by_country(country)
            ]

    def search_by_email(self, email: str) -> dict[str, Any] | None:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            fighter = uow.fighters.get_by_email(email)
            return self._to_dto(fighter).to_dict() if fighter else None

    # ── Domain operations ──────────────────────────────────────────────────────

    def upsert_medical_record(
        self, fighter_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Create or update the medical record for a fighter."""
        with UnitOfWork(session_factory=self._session_factory) as uow:
            fighter = uow.fighters.get(fighter_id)
            if fighter is None:
                raise ValueError(f"Fighter with id={fighter_id} not found.")

            if fighter.medical_record:
                mr = fighter.medical_record
                for field in ("blood_type", "doctor_name", "conditions", "notes"):
                    if field in payload:
                        setattr(mr, field, payload[field] or None)
                uow.fighters.update(fighter)
            else:
                mr = uow.fighters.add_medical_record(
                    fighter_id=fighter_id,
                    blood_type=payload.get("blood_type"),
                    notes=payload.get("notes"),
                    conditions=payload.get("conditions"),
                    doctor_name=payload.get("doctor_name"),
                )
            uow.commit()
            return MedicalRecordDTO(
                medical_record_id=mr.medical_record_id,
                fighter_id=mr.fighter_id,
                blood_type=mr.blood_type,
                notes=mr.notes,
                conditions=mr.conditions,
                doctor_name=mr.doctor_name,
            ).to_dict()

    def approve_registration(
        self, fighter_id: int, category_id: int, tournament_id: int
    ) -> dict[str, Any]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            reg = uow.fighters.approve_registration(
                fighter_id, category_id, tournament_id
            )
            uow.commit()
            return self._reg_to_dto(reg).to_dict()

    # ── Converters ─────────────────────────────────────────────────────────────

    @staticmethod
    def _to_dto(f: Fighter) -> FighterDTO:
        return FighterDTO(
            fighter_id=f.fighter_id,
            first_name=f.first_name,
            last_name=f.last_name,
            gender=f.gender,
            belt_level=f.belt_level,
            club_name=f.club_name,
            country=f.country,
            email=f.email,
            phone=f.phone,
            birth_date=f.birth_date.isoformat() if f.birth_date else None,
            created_at=f.created_at.isoformat() if f.created_at else None,
        )

    @staticmethod
    def _reg_to_dto(r: FighterCategoryRegistration) -> RegistrationDTO:
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
