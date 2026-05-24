"""
domain package — public surface.
Following BandHub: __init__.py re-exports everything consumers need.
"""

from .config import ENVIRONMENT, DB_URL, get_database_url
from .db import Base, engine, Session
from .models import (
    Fighter,
    MedicalRecord,
    Tournament,
    Tatami,
    Category,
    FighterCategoryRegistration,
    Match,
)
from .repositories import (
    FighterRepository,
    TournamentRepository,
    CategoryRepository,
    MatchRepository,
    RegistrationRepository,
    UnitOfWork,
)

__all__ = [
    # Config
    "ENVIRONMENT", "DB_URL", "get_database_url",
    # DB
    "Base", "engine", "Session",
    # Models
    "Fighter", "MedicalRecord", "Tournament", "Tatami",
    "Category", "FighterCategoryRegistration", "Match",
    # Repositories
    "FighterRepository", "TournamentRepository", "CategoryRepository",
    "MatchRepository", "RegistrationRepository", "UnitOfWork",
]
