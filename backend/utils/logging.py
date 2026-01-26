"""
Logging configuration with rotating file handler and systemd/journald support.

This module configures application-wide logging with:
- File logging to logs/app.log with rotation (5MB default, 3 backups)
- Console logging in DEBUG mode or when USE_JOURNALD=true
- Consistent log format: {timestamp} - {level} - {source} - {message}

For systemd/journald integration:
- Set USE_JOURNALD=true in environment
- Logs to stdout will be captured by journald
- View with: journalctl -u gebrauchtwaffen -f
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from backend.config import settings


# Get project root (logging.py is in backend/utils/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Log format: {timestamp} - {level} - {source} - {message}
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Simplified format for journald (journald adds its own timestamp)
JOURNALD_FORMAT = "%(levelname)s - %(name)s - %(message)s"


def setup_logging() -> None:
    """
    Configure application-wide logging with file rotation.

    Sets up:
    - Root logger with configured log level
    - RotatingFileHandler for file logging (5MB max, 3 backups)
    - StreamHandler for console output in DEBUG mode

    Log format: {timestamp} - {level} - {source} - {message}
    Example: 2026-01-22 08:00:01 - INFO - crawler - Starting crawl for 3 sources
    """
    # Determine log file path (use absolute path from project root)
    log_file = settings.LOG_FILE
    if not Path(log_file).is_absolute():
        log_file = str(PROJECT_ROOT / log_file)

    # Ensure logs directory exists
    log_dir = Path(log_file).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    # Create formatter
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    # Configure root logger
    root_logger = logging.getLogger()
    log_level = getattr(logging, settings.LOG_LEVEL, None)
    if log_level is None:
        log_level = logging.INFO
        # Use print here since logging isn't configured yet
        print(
            f"WARNING: Invalid LOG_LEVEL '{settings.LOG_LEVEL}'. "
            f"Valid levels: DEBUG, INFO, WARNING, ERROR, CRITICAL. "
            f"Falling back to INFO."
        )
    root_logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # File handler with rotation
    file_handler = RotatingFileHandler(
        filename=log_file,
        maxBytes=settings.LOG_MAX_SIZE,
        backupCount=settings.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)  # File captures all levels
    root_logger.addHandler(file_handler)

    # Console handler for DEBUG mode or journald integration
    use_journald = os.environ.get("USE_JOURNALD", "").lower() in ("true", "1", "yes")

    if settings.DEBUG or use_journald:
        console_handler = logging.StreamHandler(sys.stdout)

        # Use simplified format for journald (it adds its own timestamp)
        if use_journald:
            journald_formatter = logging.Formatter(JOURNALD_FORMAT)
            console_handler.setFormatter(journald_formatter)
        else:
            console_handler.setFormatter(formatter)

        console_handler.setLevel(logging.DEBUG)
        root_logger.addHandler(console_handler)

    # Log startup message
    root_logger.info(
        f"Logging initialized. Level: {settings.LOG_LEVEL}, "
        f"File: {log_file}, Max size: {settings.LOG_MAX_SIZE} bytes, "
        f"Backups: {settings.LOG_BACKUP_COUNT}"
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for the given name.

    Args:
        name: Logger name (typically __name__ of the calling module)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)
