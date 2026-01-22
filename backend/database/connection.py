"""
Database connection configuration for SQLite with WAL mode.

This module sets up the SQLAlchemy engine with:
- SQLite database in data/gebrauchtwaffen.db
- WAL (Write-Ahead Logging) mode for better concurrency
- check_same_thread=False for FastAPI async compatibility
"""
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker, declarative_base

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
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable WAL mode on every SQLite connection for better concurrency."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


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

    Call this on application startup to ensure tables exist.
    Note: In Story 1.4, this will be replaced by Alembic migrations.
    """
    Base.metadata.create_all(bind=engine)
