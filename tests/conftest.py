"""
conftest.py — shared pytest fixtures.

All tests use an in-memory SQLite database so no external services are needed.
"""

import os
import sys

import pytest

# ── Make the project root importable ─────────────────────────────────────────
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
)

# Switch to test environment BEFORE importing anything from src.domain
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL_TEST"] = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def db_engine():
    """Create all tables once per test session."""
    from src.domain.db import engine, Base
    import src.domain.models  # noqa: F401 — registers all models

    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def session_factory(db_engine):
    """Return a sessionmaker bound to the in-memory engine."""
    from sqlalchemy.orm import sessionmaker

    return sessionmaker(bind=db_engine, autoflush=False, autocommit=False)


@pytest.fixture
def uow(session_factory):
    """Open a UnitOfWork for each test and roll back after it finishes."""
    from src.domain.repositories import UnitOfWork

    with UnitOfWork(session_factory=session_factory) as unit:
        yield unit
        unit.rollback()
