"""
Database module - SQLite with WAL mode configuration and ORM models.
"""
from backend.database.connection import (
    Base,
    SessionLocal,
    engine,
    get_db,
    init_db,
    DATABASE_PATH,
    DATABASE_URL,
)
from backend.database.models import (
    Match,
    SearchTerm,
    Source,
    TimestampMixin,
)

__all__ = [
    # Connection
    "Base",
    "SessionLocal",
    "engine",
    "get_db",
    "init_db",
    "DATABASE_PATH",
    "DATABASE_URL",
    # Models
    "Match",
    "SearchTerm",
    "Source",
    "TimestampMixin",
]
