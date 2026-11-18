"""Clase base común para todos los servicios de negocio del servidor.

Cada servicio es sin estado (stateless): cada llamada a un método abre
su propia UnitOfWork vinculada a la factoría de sesiones, asegurando
atomicidad transaccional y aislamiento entre peticiones concurrentes.
"""

from __future__ import annotations

from typing import Any, Callable

from src.domain.repositories import UnitOfWork


class BaseService:
    """Stateless service; each method opens its own UnitOfWork."""

    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    def _uow(self) -> UnitOfWork:
        """Return a new unit of work bound to this service's sessions."""
        return UnitOfWork(session_factory=self._session_factory)
