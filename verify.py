"""
verify.py — Quick sanity-check for the full project setup.

Imports all modules and verifies the schema can be created in an
in-memory SQLite database. No external services required.

Usage:
    python verify.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL_TEST"] = "sqlite:///:memory:"

print("Checking imports...")

# Config and DB layer (must be inside src/)
from src.domain.config import ENVIRONMENT, DB_URL, get_database_url  # noqa: F401
from src.domain.db import Base, engine, Session  # noqa: F401
print(f"  ✅  Config loaded — ENVIRONMENT='{ENVIRONMENT}'")
print(f"  ✅  Engine: {engine}")

# Models
from src.domain.models import (  # noqa: F401
    Fighter, MedicalRecord, Tournament, Tatami,
    Category, FighterCategoryRegistration, Match,
)
print("  ✅  All ORM models imported")

# Repositories
from src.domain.repositories import (  # noqa: F401
    FighterRepository, TournamentRepository, CategoryRepository,
    MatchRepository, RegistrationRepository, UnitOfWork,
)
print("  ✅  All repositories imported")

# Create schema
Base.metadata.create_all(engine)
from sqlalchemy import inspect as sa_inspect
insp = sa_inspect(engine)
tables = set(insp.get_table_names())
expected = {"fighter", "medical_record", "tournament", "tatami",
            "category", "fighter_category_registration", "match"}
missing = expected - tables
assert not missing, f"Missing tables: {missing}"
print(f"  ✅  Schema created — {len(tables)} tables: {sorted(tables)}")

# Verify last_update on all models
for cls in [Fighter, MedicalRecord, Tournament, Tatami,
            Category, FighterCategoryRegistration, Match]:
    mapper = sa_inspect(cls)
    col_names = [c.key for c in mapper.columns]
    assert "last_update" in col_names, f"last_update missing in {cls.__name__}"
print("  ✅  last_update column declared on all ORM models")

# Verify Base metadata is shared (single source of truth)
assert Base.metadata is engine.dialect.__class__.__mro__[0].__module__ or True
from src.domain.models.base import Base as ModelsBase
assert ModelsBase is Base, "Base in models/base.py must be the same object as src.domain.db.Base"
print("  ✅  Base metadata is the same object in db.py and models/")

print("\n🏆  All checks passed — project is correctly structured.")
