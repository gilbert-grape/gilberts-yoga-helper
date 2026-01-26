"""
Database connection configuration for SQLite with WAL mode.

This module sets up the SQLAlchemy engine with:
- SQLite database in data/gebrauchtwaffen.db
- WAL (Write-Ahead Logging) mode for better concurrency
- check_same_thread=False for FastAPI async compatibility
"""
import logging
from pathlib import Path
from typing import Any, Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker, declarative_base

# Use standard logging.getLogger here instead of backend.utils.logging
# to avoid circular imports (backend.__init__ -> backend.utils.logging -> backend.config)
# Logging will still work correctly once setup_logging() has been called
logger = logging.getLogger(__name__)

# Get project root (connection.py is in backend/database/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATABASE_PATH = PROJECT_ROOT / "data" / "gebrauchtwaffen.db"

# Ensure data directory exists
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

# SQLite URL
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# Create engine with SQLite-specific settings
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Required for FastAPI async routes
    echo=False,  # Set True for SQL debugging
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection: Any, connection_record: Any) -> None:
    """Enable WAL mode on every SQLite connection for better concurrency."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    result = cursor.fetchone()
    cursor.close()

    # Verify WAL mode was set correctly
    if result and result[0] != "wal":
        logger.warning(
            f"Failed to enable WAL mode. Got '{result[0]}' instead of 'wal'. "
            "Database may have reduced concurrency."
        )


# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models (to be used in Story 1.3)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for FastAPI routes to get database session.

    Usage:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    Initialize database by creating all tables.

    DEPRECATED: This function is kept for backwards compatibility only.
    Use Alembic migrations instead: `alembic upgrade head`
    """
    Base.metadata.create_all(bind=engine)
