"""
SQLAlchemy ORM models for Gebrauchtwaffen Aggregator.

Models:
- SearchTerm: User's search terms with match type (exact/similar)
- Source: Scraper source websites
- Match: Found listings matching search terms

Naming Conventions (per Architecture):
- Tables: plural snake_case (search_terms, sources, matches)
- Columns: snake_case (search_term_id, match_type, created_at)
- Foreign keys: <singular>_id pattern (source_id, search_term_id)
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
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


class SearchTerm(TimestampMixin, Base):
    """
    User's search terms for finding firearms listings.

    Attributes:
        term: The search term text (e.g., "Glock 17", "SIG 550")
        match_type: How to match - "exact" or "similar"
        is_active: Whether to include in crawls
    """

    __tablename__ = "search_terms"

    term = Column(String(255), nullable=False, unique=True, index=True)
    match_type = Column(
        String(20), default="exact", nullable=False
    )  # "exact" or "similar"
    is_active = Column(Boolean, default=True, nullable=False)

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
        last_crawl_at: When the source was last crawled
        last_error: Last error message if crawl failed
    """

    __tablename__ = "sources"

    name = Column(String(100), nullable=False, unique=True, index=True)
    base_url = Column(String(500), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    last_crawl_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)

    # Relationship to matches
    matches = relationship("Match", back_populates="source", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Source(id={self.id}, name='{self.name}', is_active={self.is_active})>"


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
    external_id = Column(String(100), nullable=True, index=True)

    # Relationships
    source = relationship("Source", back_populates="matches")
    search_term = relationship("SearchTerm", back_populates="matches")

    def __repr__(self) -> str:
        return f"<Match(id={self.id}, title='{self.title[:30]}...', source_id={self.source_id})>"
