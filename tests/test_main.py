"""
Tests for main.py application startup and verification.

Tests verify:
- verify_database() handles missing database
- verify_database() handles missing alembic_version table
- verify_database() handles missing application tables
- verify_database() succeeds with complete database
"""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine, text

from alembic import command
from alembic.config import Config

from backend.database.connection import PROJECT_ROOT


ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"


class TestVerifyDatabase:
    """Tests for verify_database() function."""

    @pytest.fixture
    def mock_database_path(self, tmp_path):
        """Create a mock DATABASE_PATH that points to a temp directory."""
        db_file = tmp_path / "test.db"
        return db_file

    def test_logs_error_when_database_missing(self, mock_database_path, caplog):
        """verify_database should log error when database file doesn't exist."""
        import logging
        import backend.main

        caplog.set_level(logging.ERROR)

        # Patch DATABASE_PATH to use our temp path (file doesn't exist)
        with patch.object(backend.main, 'DATABASE_PATH', mock_database_path):
            backend.main.verify_database()

        assert "Database file not found" in caplog.text
        assert "alembic upgrade head" in caplog.text

    def test_logs_warning_when_alembic_version_missing(self, mock_database_path, caplog):
        """verify_database should log warning when alembic_version table doesn't exist."""
        import logging
        import backend.main

        caplog.set_level(logging.WARNING)

        # Create an empty database file with a dummy table
        test_engine = create_engine(
            f"sqlite:///{mock_database_path}",
            connect_args={"check_same_thread": False}
        )
        with test_engine.connect() as conn:
            conn.execute(text("CREATE TABLE dummy (id INTEGER PRIMARY KEY)"))
            conn.commit()

        with patch.object(backend.main, 'DATABASE_PATH', mock_database_path), \
             patch.object(backend.main, 'engine', test_engine):
            backend.main.verify_database()

        test_engine.dispose()
        assert "Alembic version table not found" in caplog.text

    def test_logs_warning_when_tables_missing(self, mock_database_path, caplog):
        """verify_database should log warning when application tables are missing."""
        import logging
        import backend.main

        caplog.set_level(logging.WARNING)

        # Create database with alembic_version but no app tables
        test_engine = create_engine(
            f"sqlite:///{mock_database_path}",
            connect_args={"check_same_thread": False}
        )
        with test_engine.connect() as conn:
            conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
            conn.execute(text("INSERT INTO alembic_version VALUES ('001_initial')"))
            conn.commit()

        with patch.object(backend.main, 'DATABASE_PATH', mock_database_path), \
             patch.object(backend.main, 'engine', test_engine):
            backend.main.verify_database()

        test_engine.dispose()
        assert "Missing tables" in caplog.text

    def test_succeeds_when_database_complete(self, mock_database_path):
        """verify_database should complete without warning/error when all tables exist."""
        import backend.main

        # Run actual migrations to create complete database
        alembic_cfg = Config(str(ALEMBIC_INI))
        alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{mock_database_path}")
        command.upgrade(alembic_cfg, "head")

        test_engine = create_engine(
            f"sqlite:///{mock_database_path}",
            connect_args={"check_same_thread": False}
        )

        # Mock the logger to verify the success message is logged
        with patch.object(backend.main, 'DATABASE_PATH', mock_database_path), \
             patch.object(backend.main, 'engine', test_engine), \
             patch.object(backend.main.logger, 'info') as mock_info, \
             patch.object(backend.main.logger, 'warning') as mock_warning, \
             patch.object(backend.main.logger, 'error') as mock_error:
            backend.main.verify_database()

            # Should log success info, no warnings or errors
            mock_info.assert_called_once()
            assert "Database verification successful" in mock_info.call_args[0][0]
            mock_warning.assert_not_called()
            mock_error.assert_not_called()

        test_engine.dispose()

    def test_raises_on_connection_error(self, mock_database_path):
        """verify_database should raise exception on database connection error."""
        import backend.main

        # Create database file so it passes existence check
        mock_database_path.touch()

        # Create a mock engine that raises on connect
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = Exception("Connection failed")

        with patch.object(backend.main, 'DATABASE_PATH', mock_database_path), \
             patch.object(backend.main, 'engine', mock_engine):
            with pytest.raises(Exception, match="Connection failed"):
                backend.main.verify_database()
