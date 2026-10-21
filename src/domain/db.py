"""
Database engine and session factory.
Follows the BandHub pattern: db.py lives inside src/domain/.

Exports:
    Base     — shared DeclarativeBase for all ORM models
    engine   — SQLAlchemy engine wired to the current environment
    Session  — configured sessionmaker
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_database_url


# ── Shared declarative base ──────────────────────────────────────────────────
class Base(DeclarativeBase):
    """All ORM models inherit from this base."""


# ── Engine ───────────────────────────────────────────────────────────────────
def _build_engine(echo: bool = False):
    url = get_database_url()
    connect_args = {"check_same_thread": False} if "sqlite" in url else {}
    eng = create_engine(url, echo=echo, connect_args=connect_args)

    # Enable FK enforcement for SQLite
    if "sqlite" in url:

        @event.listens_for(eng, "connect")
        def _set_sqlite_pragma(dbapi_conn, _record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return eng


engine = _build_engine()

# ── Session factory ──────────────────────────────────────────────────────────
Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
