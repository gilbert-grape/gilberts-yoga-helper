"""
Services Package

Business logic services for Gebrauchtwaffen Aggregator.

Exports:
    - MatchResult: TypedDict for match results
    - normalize_text: Normalize text for similar matching
    - matches_exact: Check exact match
    - matches_similar: Check similar match
    - matches: Check match with specified type
    - find_matches: Find all matches between listings and search terms
    - CrawlResult: Dataclass for crawl results
    - run_crawl: Run complete crawl orchestration
    - get_registered_sources: Get list of registered source names
    - ensure_sources_exist: Create missing sources in database
    - SCRAPER_REGISTRY: Mapping of source names to scraper functions
"""
from backend.services.matching import (
    MatchResult,
    find_matches,
    matches,
    matches_exact,
    matches_similar,
    normalize_text,
)
from backend.services.crawler import (
    CrawlResult,
    run_crawl,
    run_crawl_async,
    get_registered_sources,
    ensure_sources_exist,
    SCRAPER_REGISTRY,
)

__all__ = [
    # Matching
    "MatchResult",
    "find_matches",
    "matches",
    "matches_exact",
    "matches_similar",
    "normalize_text",
    # Crawler
    "CrawlResult",
    "run_crawl",
    "run_crawl_async",
    "get_registered_sources",
    "ensure_sources_exist",
    "SCRAPER_REGISTRY",
]
