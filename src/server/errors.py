"""Errores tipados de la aplicación lanzados por las capas del servidor.

Todas las excepciones heredan de ``ValueError`` para mantener compatibilidad
con manejadores generales (``except ValueError``), permitiendo a su vez que el
Router traduzca cada subclase a su código estructurado (``error_code``).
"""

from __future__ import annotations

from src.common.protocol import ErrorCode


class AppError(ValueError):
    """Base class for expected, client-caused failures."""

    code = ErrorCode.BAD_REQUEST


class ValidationError(AppError):
    """A field is missing, has the wrong type or an invalid value."""

    code = ErrorCode.VALIDATION_ERROR


class NotFoundError(AppError):
    """The requested entity does not exist."""

    code = ErrorCode.NOT_FOUND


class ConflictError(AppError):
    """The operation conflicts with existing data (e.g. duplicates)."""

    code = ErrorCode.CONFLICT


class UnknownActionError(AppError):
    """The action is not supported for the requested resource."""

    code = ErrorCode.UNKNOWN_ACTION
