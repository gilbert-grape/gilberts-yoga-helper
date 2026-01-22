"""
Tests for database connection configuration.

Tests verify:
- SQLite database is created at the correct path
- WAL mode is enabled
- Session factory works correctly
- check_same_thread is disabled for async compatibility
"""
import pytest
from pathlib import Path
from sqlalchemy import text

from backend.database.connection import (
    engine,
    SessionLocal,
    Base,
    get_db,
    init_db,
    DATABASE_PATH,
    DATABASE_URL,
)


class TestDatabasePath:
    """Tests for database file path configuration."""

    def test_database_path_is_absolute(self):
        """Database path should be an absolute path."""
        assert DATABASE_PATH.is_absolute()

    def test_database_path_in_data_directory(self):
        """Database should be in the data/ directory."""
        assert DATABASE_PATH.parent.name == "data"

    def test_database_filename_correct(self):
        """Database filename should be gebrauchtwaffen.db."""
        assert DATABASE_PATH.name == "gebrauchtwaffen.db"

    def test_database_url_format(self):
        """DATABASE_URL should be a valid SQLite URL."""
        assert DATABASE_URL.startswith("sqlite:///")
        assert "gebrauchtwaffen.db" in DATABASE_URL


class TestWALMode:
    """Tests for WAL (Write-Ahead Logging) mode configuration."""

    def test_wal_mode_enabled(self):
        """WAL mode should be enabled on database connection."""
        with engine.connect() as conn:
            result = conn.execute(text("PRAGMA journal_mode"))
            mode = result.scalar()
            assert mode == "wal", f"Expected 'wal', got '{mode}'"

    def test_wal_mode_persists_across_connections(self):
        """WAL mode should be enabled on every new connection."""
        # First connection
        with engine.connect() as conn1:
            result1 = conn1.execute(text("PRAGMA journal_mode"))
            mode1 = result1.scalar()

        # Second connection (new connection from pool)
        with engine.connect() as conn2:
            result2 = conn2.execute(text("PRAGMA journal_mode"))
            mode2 = result2.scalar()

        assert mode1 == "wal"
        assert mode2 == "wal"


class TestSessionFactory:
    """Tests for SessionLocal factory."""

    def test_session_can_be_created(self):
        """SessionLocal should create valid database sessions."""
        session = SessionLocal()
        try:
            # Simple query to verify session works
            result = session.execute(text("SELECT 1"))
            assert result.scalar() == 1
        finally:
            session.close()

    def test_get_db_yields_session(self):
        """get_db dependency should yield a working session."""
        db_gen = get_db()
        session = next(db_gen)
        try:
            result = session.execute(text("SELECT 1"))
            assert result.scalar() == 1
        finally:
            # Clean up generator
            try:
                next(db_gen)
            except StopIteration:
                pass


class TestCheckSameThread:
    """Tests for check_same_thread configuration."""

    def test_engine_allows_cross_thread_access(self):
        """Engine should be configured with check_same_thread=False."""
        # This is verified by the engine's connect_args
        # If check_same_thread was True, we'd get threading errors in async context
        import threading

        result_from_thread = []
        error_from_thread = []

        def query_in_thread():
            try:
                with engine.connect() as conn:
                    result = conn.execute(text("SELECT 1"))
                    result_from_thread.append(result.scalar())
            except Exception as e:
                error_from_thread.append(str(e))

        thread = threading.Thread(target=query_in_thread)
        thread.start()
        thread.join()

        assert len(error_from_thread) == 0, f"Thread error: {error_from_thread}"
        assert result_from_thread == [1]


class TestInitDb:
    """Tests for database initialization."""

    def test_init_db_creates_tables(self):
        """init_db should create tables without error."""
        # This should not raise any errors
        init_db()
        # Verify we can still query
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.scalar() == 1

    def test_data_directory_exists(self):
        """Data directory should be created if it doesn't exist."""
        assert DATABASE_PATH.parent.exists()
        assert DATABASE_PATH.parent.is_dir()
