"""Business operations for the Category domain."""

from __future__ import annotations

from typing import Any, Optional

from src.domain.models import Category
from src.server.converters import category_to_dto, to_dicts
from src.server.errors import NotFoundError, ValidationError
from src.server.services.base import BaseService
from src.server.validation import clean_str, optional_number


class CategoryService(BaseService):
    """CRUD and searches for categories."""

    # -- CRUD ----------------------------------------------------------

    def list_all(self) -> list[dict[str, Any]]:
        with self._uow() as uow:
            return to_dicts(uow.categories.get_all(), category_to_dto)

    def get_by_id(self, category_id: int) -> dict[str, Any] | None:
        with self._uow() as uow:
            category = uow.categories.get(category_id)
            if category is None:
                return None
            result = category_to_dto(category).to_dict()
            result["total_registrations"] = len(category.registrations)
            result["total_matches"] = len(category.matches)
            return result

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = clean_str(payload.get("name"))
        if not name:
            raise ValidationError("name is required.")
        weight_min = optional_number(payload, "weight_min_kg")
        weight_max = optional_number(payload, "weight_max_kg")
        with self._uow() as uow:
            category = Category(
                name=name,
                belt_level=payload.get("belt_level"),
                gender=payload.get("gender"),
                weight_min_kg=weight_min,
                weight_max_kg=weight_max,
            )
            uow.categories.add(category)
            uow.commit()
            return category_to_dto(category).to_dict()

    def update(
        self, category_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        weights = {
            name: optional_number(payload, name)
            for name in ("weight_min_kg", "weight_max_kg")
            if name in payload
        }
        with self._uow() as uow:
            category = self._get_or_raise(uow, category_id)
            name = clean_str(payload.get("name"))
            if name:
                category.name = name
            for field in ("belt_level", "gender"):
                if field in payload:
                    setattr(category, field, payload[field] or None)
            for field, value in weights.items():
                setattr(category, field, value)
            uow.categories.update(category)
            uow.commit()
            return category_to_dto(category).to_dict()

    def delete(self, category_id: int) -> None:
        with self._uow() as uow:
            category = self._get_or_raise(uow, category_id)
            uow.categories.delete(category)
            uow.commit()

    # -- Searches ------------------------------------------------------

    def search_by_name(self, name: str) -> list[dict[str, Any]]:
        with self._uow() as uow:
            found = uow.categories.get_by_name(name)
            return to_dicts(found, category_to_dto)

    def search_by_belt_level(self, belt_level: str) -> list[dict[str, Any]]:
        with self._uow() as uow:
            found = uow.categories.get_by_belt_level(belt_level)
            return to_dicts(found, category_to_dto)

    def search_by_gender(self, gender: str) -> list[dict[str, Any]]:
        with self._uow() as uow:
            found = uow.categories.get_by_gender(gender)
            return to_dicts(found, category_to_dto)

    def search_by_weight_range(
        self,
        min_kg: Optional[float] = None,
        max_kg: Optional[float] = None,
    ) -> list[dict[str, Any]]:
        with self._uow() as uow:
            found = uow.categories.get_by_weight_range(
                min_kg=min_kg, max_kg=max_kg
            )
            return to_dicts(found, category_to_dto)

    # -- Internals -----------------------------------------------------

    @staticmethod
    def _get_or_raise(uow, category_id: int) -> Category:
        category = uow.categories.get(category_id)
        if category is None:
            raise NotFoundError(f"Category with id={category_id} not found.")
        return category
