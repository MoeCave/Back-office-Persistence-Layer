"""Configuración de base de datos — Selección dinámica de URL de entorno.

Permite alternar entornos mediante la variable `APP_ENV`:
    APP_ENV=test         → SQLite local en memoria/archivo
    APP_ENV=development  → PostgreSQL local (Docker Compose)
    APP_ENV=production   → PostgreSQL en producción
"""

import os
from dotenv import load_dotenv

load_dotenv()

ENVIRONMENT: str = os.getenv("APP_ENV", "development")

DB_URL: str | None = {
    "test": os.getenv("DATABASE_URL_TEST", "sqlite:///./test_tournament.db"),
    "development": os.getenv("DATABASE_URL_DEVELOPMENT"),
    "production": os.getenv("DATABASE_URL_PRODUCTION"),
}.get(ENVIRONMENT)


def get_database_url() -> str:
    """Return the database URL for the current environment.

    Raises ValueError if no URL is configured for the active environment.
    """
    if not DB_URL:
        raise ValueError(
            f"No DATABASE_URL configured for environment '{ENVIRONMENT}'. "
            "Check your .env file and make sure DATABASE_URL_DEVELOPMENT or "
            "DATABASE_URL_PRODUCTION is set."
        )
    return DB_URL
