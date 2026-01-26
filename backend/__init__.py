"""
Backend package initialization.

Initializes logging early to ensure all modules have properly configured logging.
"""
from backend.utils.logging import setup_logging

# Initialize logging on package import
# This ensures logging is configured before any other module uses logging
setup_logging()
