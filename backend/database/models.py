"""
SQLAlchemy ORM models for Gebrauchtwaffen Aggregator.

Models:
- SearchTerm: User's search terms with match type (exact/similar)
- Source: Scraper source websites
- Match: Found listings matching search terms
- AppSettings: Application-wide settings (last_seen_at for new match detection)
- CrawlLog: History of crawl executions

Naming Conventions (per Architecture):
- Tables: plural snake_case (search_terms, sources, matches)
- Columns: snake_case (search_term_id, match_type, created_at)
- Foreign keys: <singular>_id pattern (source_id, search_term_id)
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from backend.database.connection import Base


class TimestampMixin:
    """
    Mixin providing id and timestamp columns for all models.

    All models inherit from this to ensure consistent:
    - Primary key (id)
    - Creation timestamp (created_at)
    - Update timestamp (updated_at)
    """

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class ExcludeTerm(TimestampMixin, Base):
    """
    Negative keywords to exclude from search results.

    If a listing title contains any of these terms, it will be excluded
    from the search results even if it matches a search term.

    Attributes:
        term: The exclusion term text (e.g., "Softair", "Airsoft", "CO2")
        is_active: Whether this exclusion is active
    """

    __tablename__ = "exclude_terms"

    term = Column(String(255), nullable=False, unique=True, index=True)
    is_active = Column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<ExcludeTerm(id={self.id}, term='{self.term}', is_active={self.is_active})>"


class SearchTerm(TimestampMixin, Base):
    """
    User's search terms for finding firearms listings.

    Attributes:
        term: The search term text (e.g., "Glock 17", "SIG 550")
        match_type: How to match - "exact" or "similar"
        is_active: Whether to include in crawls
        sort_order: Order for display and search execution (lower = first)
        hide_seen_matches: If True, matches already shown by earlier search terms
                          (by sort_order) will be hidden in the dashboard
    """

    __tablename__ = "search_terms"
    __table_args__ = (
        CheckConstraint(
            "match_type IN ('exact', 'similar')",
            name="check_match_type_valid",
        ),
    )

    term = Column(String(255), nullable=False, unique=True, index=True)
    match_type = Column(
        String(20), default="exact", nullable=False
    )  # "exact" or "similar"
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False, index=True)
    hide_seen_matches = Column(Boolean, default=True, nullable=False)

    # Relationship to matches
    matches = relationship("Match", back_populates="search_term", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<SearchTerm(id={self.id}, term='{self.term}', match_type='{self.match_type}')>"


class Source(TimestampMixin, Base):
    """
    Scraper source website configuration.

    Attributes:
        name: Display name (e.g., "waffenboerse.ch")
        base_url: Website base URL for the scraper
        is_active: Whether to include in crawls
        sort_order: Order in which sources are crawled (lower = first)
        last_crawl_at: When the source was last crawled
        last_error: Last error message if crawl failed
    """

    __tablename__ = "sources"

    name = Column(String(100), nullable=False, unique=True, index=True)
    base_url = Column(String(500), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    last_crawl_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)

    # Relationship to matches
    matches = relationship("Match", back_populates="source", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Source(id={self.id}, name='{self.name}', is_active={self.is_active})>"


class AppSettings(TimestampMixin, Base):
    """
    Application settings - single row table for app-wide state.

    This table stores application-level settings like last_seen_at
    for tracking when the user last viewed the dashboard.

    Attributes:
        last_seen_at: When the user last viewed the dashboard
    """

    __tablename__ = "app_settings"

    last_seen_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<AppSettings(id={self.id}, last_seen_at={self.last_seen_at})>"


class CrawlLog(TimestampMixin, Base):
    """
    Log entry for each crawl execution.

    Records when crawls were run (manually or via cronjob) and their results.

    Attributes:
        started_at: When the crawl started
        completed_at: When the crawl finished (null if still running or cancelled)
        status: 'running', 'success', 'partial', 'failed', 'cancelled'
        sources_attempted: Number of sources tried
        sources_succeeded: Number of sources that worked
        sources_failed: Number of sources that failed
        total_listings: Total listings scraped
        new_matches: New matches saved
        duplicate_matches: Duplicates skipped
        duration_seconds: How long the crawl took
        trigger: 'manual' or 'cronjob'
    """

    __tablename__ = "crawl_logs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'success', 'partial', 'failed', 'cancelled')",
            name="check_crawl_status_valid",
        ),
        CheckConstraint(
            "trigger IN ('manual', 'cronjob')",
            name="check_crawl_trigger_valid",
        ),
    )

    started_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="running", nullable=False)
    sources_attempted = Column(Integer, default=0, nullable=False)
    sources_succeeded = Column(Integer, default=0, nullable=False)
    sources_failed = Column(Integer, default=0, nullable=False)
    total_listings = Column(Integer, default=0, nullable=False)
    new_matches = Column(Integer, default=0, nullable=False)
    duplicate_matches = Column(Integer, default=0, nullable=False)
    duration_seconds = Column(Integer, default=0, nullable=False)
    trigger = Column(String(20), default="manual", nullable=False)

    def __repr__(self) -> str:
        return f"<CrawlLog(id={self.id}, status='{self.status}', started_at={self.started_at})>"


class Match(TimestampMixin, Base):
    """
    A found listing that matches a search term.

    Attributes:
        source_id: FK to the source website
        search_term_id: FK to the matched search term
        title: Listing title
        price: Price as string (for flexibility with formats)
        url: Direct link to the listing
        image_url: Thumbnail image URL
        is_new: Whether this is a newly found match (for highlighting)
        external_id: Source's listing ID (for deduplication)
    """

    __tablename__ = "matches"

    # Foreign keys (using <singular>_id pattern per architecture)
    source_id = Column(
        Integer, ForeignKey("sources.id"), nullable=False, index=True
    )
    search_term_id = Column(
        Integer, ForeignKey("search_terms.id"), nullable=False, index=True
    )

    # Listing data
    title = Column(String(500), nullable=False)
    price = Column(String(50), nullable=True)
    url = Column(String(1000), nullable=False)
    image_url = Column(String(1000), nullable=True)
    is_new = Column(Boolean, default=True, nullable=False)
    is_favorite = Column(Boolean, default=False, nullable=False, index=True)
    external_id = Column(String(100), nullable=True, index=True)

    # Relationships
    source = relationship("Source", back_populates="matches")
    search_term = relationship("SearchTerm", back_populates="matches")

    def __repr__(self) -> str:
        title_display = self.title[:30] + "..." if len(self.title) > 30 else self.title
        return f"<Match(id={self.id}, title='{title_display}', source_id={self.source_id})>"
