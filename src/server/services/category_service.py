"""Operaciones de negocio para el agregado Category.

Gestiona las divisiones de cinturón, peso y género, así como filtros de
búsqueda por rango de peso.

Patrón común a todos los métodos: abrir una UnitOfWork, operar con los
repositorios, convertir a DTO DENTRO del ``with`` (la sesión debe seguir
abierta para leer atributos/relaciones) y devolver diccionarios planos.
"""

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
        """Devuelve todas las categorías como lista de DTOs (dict)."""
        with self._uow() as uow:
            return to_dicts(uow.categories.get_all(), category_to_dto)

    def get_by_id(self, category_id: int) -> dict[str, Any] | None:
        """Devuelve una categoría con contadores de relaciones, o ``None``.

        Añade ``total_registrations`` y ``total_matches``. Nota: usa
        ``len()`` sobre las relaciones, lo que carga todas las filas en
        memoria; un ``COUNT`` en SQL escalaría mejor.
        """
        with self._uow() as uow:
            category = uow.categories.get(category_id)
            if category is None:
                return None
            result = category_to_dto(category).to_dict()
            result["total_registrations"] = len(category.registrations)
            result["total_matches"] = len(category.matches)
            return result

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Crea una categoría.

        Requiere ``name``; ``weight_min_kg``/``weight_max_kg`` deben ser
        numéricos finitos si se envían. No comprueba que min <= max.

        Raises:
            ValidationError: nombre vacío o peso no numérico.
        """
        name = clean_str(payload.get("name"))
        if not name:
            raise ValidationError("name is required.")
        # Se validan los pesos ANTES de abrir la UoW para fallar rápido.
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
        """Actualiza solo los campos presentes en *payload*.

        Semántica: una clave ausente no se toca; ``belt_level``/``gender``
        vacíos se guardan como ``None``; ``name`` vacío se ignora.

        Raises:
            NotFoundError: la categoría no existe.
            ValidationError: algún peso no es numérico.
        """
        # Validación previa de pesos (solo los presentes en el payload).
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
        """Elimina la categoría (y en cascada sus inscripciones).

        Los combates asociados no se borran: su ``category_id`` pasa a NULL
        (``ondelete="SET NULL"``).

        Raises:
            NotFoundError: la categoría no existe.
        """
        with self._uow() as uow:
            category = self._get_or_raise(uow, category_id)
            uow.categories.delete(category)
            uow.commit()

    # -- Searches ------------------------------------------------------

    def search_by_name(self, name: str) -> list[dict[str, Any]]:
        """Busca por nombre (coincidencia parcial, sin distinguir mayúsculas)."""
        with self._uow() as uow:
            found = uow.categories.get_by_name(name)
            return to_dicts(found, category_to_dto)

    def search_by_belt_level(self, belt_level: str) -> list[dict[str, Any]]:
        """Busca categorías de un nivel de cinturón exacto."""
        with self._uow() as uow:
            found = uow.categories.get_by_belt_level(belt_level)
            return to_dicts(found, category_to_dto)

    def search_by_gender(self, gender: str) -> list[dict[str, Any]]:
        """Busca categorías de un género exacto."""
        with self._uow() as uow:
            found = uow.categories.get_by_gender(gender)
            return to_dicts(found, category_to_dto)

    def search_by_weight_range(
        self,
        min_kg: Optional[float] = None,
        max_kg: Optional[float] = None,
    ) -> list[dict[str, Any]]:
        """Busca categorías contenidas en el rango de peso indicado.

        Cualquiera de los límites puede ser ``None`` (sin cota). Es
        inclusión estricta: ``weight_min_kg >= min_kg`` y
        ``weight_max_kg <= max_kg``, no solape de rangos.
        """
        with self._uow() as uow:
            found = uow.categories.get_by_weight_range(
                min_kg=min_kg, max_kg=max_kg
            )
            return to_dicts(found, category_to_dto)

    # -- Internals -----------------------------------------------------

    @staticmethod
    def _get_or_raise(uow, category_id: int) -> Category:
        """Obtiene la categoría o lanza ``NotFoundError`` (→ NOT_FOUND)."""
        category = uow.categories.get(category_id)
        if category is None:
            raise NotFoundError(f"Category with id={category_id} not found.")
        return category