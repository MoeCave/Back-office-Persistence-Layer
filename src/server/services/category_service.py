"""
services/category_service.py — business operations for the Category domain.
"""

from __future__ import annotations

from typing import Any, Optional

from src.domain.models import Category
from src.domain.repositories import UnitOfWork
from src.server.dto import CategoryDTO


class CategoryService:
    """Stateless service; each method opens its own UnitOfWork."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    # ── CRUD ───────────────────────────────────────────────────────────────────

    def list_all(self) -> list[dict[str, Any]]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            return [self._to_dto(c).to_dict() for c in uow.categories.get_all()]

    def get_by_id(self, category_id: int) -> dict[str, Any] | None:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            c = uow.categories.get(category_id)
            if c is None:
                return None
            result = self._to_dto(c).to_dict()
            result["total_registrations"] = len(c.registrations)
            result["total_matches"] = len(c.matches)
            return result

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = payload.get("name", "").strip()
        if not name:
            raise ValueError("name is required.")
        with UnitOfWork(session_factory=self._session_factory) as uow:
            c = Category(
                name=name,
                belt_level=payload.get("belt_level"),
                gender=payload.get("gender"),
                weight_min_kg=payload.get("weight_min_kg"),
                weight_max_kg=payload.get("weight_max_kg"),
            )
            uow.categories.add(c)
            uow.commit()
            return self._to_dto(c).to_dict()

    def update(self, category_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            c = uow.categories.get(category_id)
            if c is None:
                raise ValueError(f"Category with id={category_id} not found.")
            if "name" in payload and payload["name"]:
                c.name = payload["name"]
            for field in ("belt_level", "gender"):
                if field in payload:
                    setattr(c, field, payload[field] or None)
            for field in ("weight_min_kg", "weight_max_kg"):
                if field in payload:
                    setattr(c, field, payload[field])
            uow.categories.update(c)
            uow.commit()
            return self._to_dto(c).to_dict()

    def delete(self, category_id: int) -> None:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            c = uow.categories.get(category_id)
            if c is None:
                raise ValueError(f"Category with id={category_id} not found.")
            uow.categories.delete(c)
            uow.commit()

    # ── Searches ───────────────────────────────────────────────────────────────

    def search_by_name(self, name: str) -> list[dict[str, Any]]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            return [
                self._to_dto(c).to_dict()
                for c in uow.categories.get_by_name(name)
            ]

    def search_by_belt_level(self, belt_level: str) -> list[dict[str, Any]]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            return [
                self._to_dto(c).to_dict()
                for c in uow.categories.get_by_belt_level(belt_level)
            ]

    def search_by_gender(self, gender: str) -> list[dict[str, Any]]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            return [
                self._to_dto(c).to_dict()
                for c in uow.categories.get_by_gender(gender)
            ]

    def search_by_weight_range(
        self,
        min_kg: Optional[float] = None,
        max_kg: Optional[float] = None,
    ) -> list[dict[str, Any]]:
        with UnitOfWork(session_factory=self._session_factory) as uow:
            return [
                self._to_dto(c).to_dict()
                for c in uow.categories.get_by_weight_range(
                    min_kg=min_kg, max_kg=max_kg
                )
            ]

    # ── Converters ─────────────────────────────────────────────────────────────

    @staticmethod
    def _to_dto(c: Category) -> CategoryDTO:
        return CategoryDTO(
            category_id=c.category_id,
            name=c.name,
            belt_level=c.belt_level,
            weight_min_kg=c.weight_min_kg,
            weight_max_kg=c.weight_max_kg,
            gender=c.gender,
        )
