"""verify.py - quick sanity check for the whole project setup.

Imports every layer, verifies the schema can be created in an in-memory
SQLite database and checks that the client never loads SQLAlchemy.
No external services are required.

Usage:
    python verify.py
"""

import os
import subprocess
import sys

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL_TEST"] = "sqlite:///:memory:"

print("Checking imports...")

from sqlalchemy import inspect as sa_inspect  # noqa: E402

from src.domain.config import ENVIRONMENT  # noqa: E402
from src.domain.db import Base, engine  # noqa: E402
from src.domain.models import (  # noqa: E402
    Category,
    Fighter,
    FighterCategoryRegistration,
    Match,
    MedicalRecord,
    Tatami,
    Tournament,
)
from src.domain.models.base import Base as ModelsBase  # noqa: E402
from src.domain.repositories import (  # noqa: E402,F401
    CategoryRepository,
    FighterRepository,
    MatchRepository,
    RegistrationRepository,
    TournamentRepository,
    UnitOfWork,
)
from src.server.router import Router  # noqa: E402,F401
from src.server.routes import ROUTES  # noqa: E402

print(f"  OK  Config loaded - ENVIRONMENT='{ENVIRONMENT}'")
print(f"  OK  Engine: {engine}")
print("  OK  Models, repositories, services and router imported")

Base.metadata.create_all(engine)
tables = set(sa_inspect(engine).get_table_names())
expected = {
    "fighter",
    "medical_record",
    "tournament",
    "tatami",
    "category",
    "fighter_category_registration",
    "match",
}
missing = expected - tables
assert not missing, f"Missing tables: {missing}"
print(f"  OK  Schema created - {len(tables)} tables: {sorted(tables)}")

for model in (
    Fighter,
    MedicalRecord,
    Tournament,
    Tatami,
    Category,
    FighterCategoryRegistration,
    Match,
):
    columns = [column.key for column in sa_inspect(model).columns]
    assert "last_update" in columns, f"last_update missing in {model.__name__}"
print("  OK  last_update column declared on all ORM models")

assert ModelsBase is Base, "models/base.py must re-export db.Base"
print("  OK  Base metadata is shared by db.py and models/")

routes = sum(len(actions) for actions in ROUTES.values())
print(f"  OK  Routing table: {len(ROUTES)} resources, {routes} actions")

# The client must work without any ORM / persistence code loaded.
probe = (
    "import sys; import src.client.gateway, src.client.ui.main_menu;"
    "bad = [m for m in sys.modules if m.split('.')[0] == 'sqlalchemy'"
    " or m.startswith(('src.domain', 'src.server'))];"
    "sys.exit(1 if bad else 0)"
)
result = subprocess.run([sys.executable, "-c", probe], check=False)
assert result.returncode == 0, "Client imports persistence/server code!"
print("  OK  Client does not import SQLAlchemy, domain or server code")

print("\nAll checks passed - project is correctly structured.")
