"""
Application configuration loaded from environment variables.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application settings."""

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///data/gebrauchtwaffen.db")

    # Application
    APP_NAME: str = "Gebrauchtwaffen Aggregator"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Scraper settings
    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "30"))
    REQUEST_DELAY_MIN: int = int(os.getenv("REQUEST_DELAY_MIN", "2"))
    REQUEST_DELAY_MAX: int = int(os.getenv("REQUEST_DELAY_MAX", "5"))
    USER_AGENT: str = os.getenv(
        "USER_AGENT",
        "Mozilla/5.0 (compatible; GebrauchtWaffenBot/1.0)"
    )


settings = Settings()
