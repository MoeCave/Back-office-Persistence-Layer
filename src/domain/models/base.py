"""
Shared declarative base — re-exported from src.domain.db.

All models import Base from here so there is a single source of truth:
    from .base import Base

The actual Base class lives in src/domain/db.py so that Alembic,
the engine, and the models all share the exact same metadata object.
"""

from src.domain.db import Base  # single source of truth

__all__ = ["Base"]
