"""
Crawler Orchestrator for Gebrauchtwaffen Aggregator.

Coordinates scraping all active sources, matching results against
search terms, and saving matches to the database.

Key features:
- Sequential execution (not parallel) for Pi resource constraints
- Error isolation: one scraper failure doesn't stop others
- Comprehensive logging and result tracking
"""
import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.database.crud import (
    create_crawl_log,
    get_active_search_terms,
    get_active_sources,
    get_or_create_source,
    save_matches,
    search_term_to_dict,
    update_crawl_log,
)
from backend.database.models import Source
from backend.scrapers import (
    ScraperResults,
    scrape_aats,
    scrape_aebiwaffen,
    scrape_armashop,
    scrape_egun,
    scrape_ellie,
    scrape_gwmh,
    scrape_petitesannonces,
    scrape_renehild,
    scrape_vnsm,
    scrape_waffenboerse,
    scrape_waffengebraucht,
    scrape_waffenjoray,
    scrape_waffenzimmi,
)
from backend.services.matching import find_matches
from backend.utils.logging import get_logger

logger = get_logger(__name__)


# Type alias for async scraper functions
AsyncScraperFunc = Callable[[], Awaitable[ScraperResults]]

# Registry mapping source names to their scraper functions
# Source names must match database source.name values
SCRAPER_REGISTRY: Dict[str, AsyncScraperFunc] = {
    "aats-group.ch": scrape_aats,
    "aebiwaffen.ch": scrape_aebiwaffen,
    "armashop.ch": scrape_armashop,
    "egun.de": scrape_egun,
    "ellie-firearms.com": scrape_ellie,
    "gwmh-shop.ch": scrape_gwmh,
    "petitesannonces.ch": scrape_petitesannonces,
    "renehild-tactical.ch": scrape_renehild,
    "vnsm.ch": scrape_vnsm,
    "waffenboerse.ch": scrape_waffenboerse,
    "waffengebraucht.ch": scrape_waffengebraucht,
    "waffen-joray.ch": scrape_waffenjoray,
    "waffenzimmi.ch": scrape_waffenzimmi,
}

# Base URLs for each source (used when creating sources)
SOURCE_BASE_URLS: Dict[str, str] = {
    "aats-group.ch": "https://aats-group.ch",
    "aebiwaffen.ch": "https://www.aebiwaffen.ch",
    "armashop.ch": "https://armashop.ch",
    "egun.de": "https://egun.de/market",
    "ellie-firearms.com": "https://ellie-firearms.com",
    "gwmh-shop.ch": "https://www.gwmh-shop.ch",
    "petitesannonces.ch": "https://www.petitesannonces.ch",
    "renehild-tactical.ch": "https://renehild-tactical.ch",
    "vnsm.ch": "https://www.vnsm.ch",
    "waffenboerse.ch": "https://www.waffenboerse.ch",
    "waffengebraucht.ch": "https://waffengebraucht.ch",
    "waffen-joray.ch": "https://waffen-joray.ch",
    "waffenzimmi.ch": "https://www.waffenzimmi.ch",
}


@dataclass
class CrawlResult:
    """Result of a complete crawl run."""

    sources_attempted: int = 0
    sources_succeeded: int = 0
    sources_failed: int = 0
    total_listings: int = 0
    new_matches: int = 0
    duplicate_matches: int = 0
    failed_sources: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def __str__(self) -> str:
        return (
            f"CrawlResult(attempted={self.sources_attempted}, "
            f"succeeded={self.sources_succeeded}, failed={self.sources_failed}, "
            f"listings={self.total_listings}, new_matches={self.new_matches}, "
            f"duplicates={self.duplicate_matches}, duration={self.duration_seconds:.1f}s)"
        )

    @property
    def is_success(self) -> bool:
        """Check if crawl was fully successful (no failures)."""
        return self.sources_failed == 0 and self.sources_attempted > 0

    @property
    def is_partial_success(self) -> bool:
        """Check if crawl had some failures but also some successes."""
        return self.sources_failed > 0 and self.sources_succeeded > 0

    @property
    def status_text(self) -> str:
        """Get human-readable status text."""
        if self.sources_attempted == 0:
            return "Keine Quellen"
        if self.is_success:
            return "Erfolgreich"
        if self.is_partial_success:
            return "Teilweise erfolgreich"
        return "Fehlgeschlagen"


@dataclass
class CrawlState:
    """
    Global crawl state for tracking running crawls.

    This is a simple in-memory state for single-user Pi deployment.
    """

    is_running: bool = False
    cancel_requested: bool = False
    last_result: Optional[CrawlResult] = None
    current_source: Optional[str] = None
    log_messages: List[str] = field(default_factory=list)


# Global crawl state (single instance for single-user app)
_crawl_state = CrawlState()


def add_crawl_log(message: str) -> None:
    """Add a log message to the current crawl state."""
    from datetime import datetime
    timestamp = datetime.now().strftime("%H:%M:%S")
    _crawl_state.log_messages.append(f"[{timestamp}] {message}")


def clear_crawl_log() -> None:
    """Clear all log messages."""
    _crawl_state.log_messages.clear()


def get_crawl_log() -> List[str]:
    """Get all log messages."""
    return _crawl_state.log_messages.copy()


def get_registered_sources() -> List[str]:
    """Get list of all registered source names."""
    return list(SCRAPER_REGISTRY.keys())


def get_crawl_state() -> CrawlState:
    """Get the current crawl state."""
    return _crawl_state


def is_crawl_running() -> bool:
    """Check if a crawl is currently running."""
    return _crawl_state.is_running


def request_crawl_cancel() -> bool:
    """
    Request cancellation of the currently running crawl.

    Returns:
        True if a crawl was running and cancellation was requested,
        False if no crawl is running.
    """
    if _crawl_state.is_running:
        _crawl_state.cancel_requested = True
        logger.info("Crawl cancellation requested")
        return True
    return False


def prepare_crawl_state() -> bool:
    """
    Prepare the crawl state before starting a background crawl.

    This sets is_running=True, clears the log, and adds an initial message.
    Must be called BEFORE creating the background task to avoid race conditions.

    Returns:
        True if state was prepared successfully,
        False if a crawl is already running.
    """
    global _crawl_state

    if _crawl_state.is_running:
        return False

    _crawl_state.is_running = True
    _crawl_state.cancel_requested = False
    _crawl_state.current_source = None
    clear_crawl_log()
    add_crawl_log("Crawl wird gestartet...")

    return True


def is_cancel_requested() -> bool:
    """Check if cancellation has been requested."""
    return _crawl_state.cancel_requested


def get_last_crawl_result() -> Optional[CrawlResult]:
    """Get the result of the last completed crawl."""
    return _crawl_state.last_result


def ensure_sources_exist(session: Session) -> Dict[str, int]:
    """
    Ensure all registered sources exist in the database.

    Creates any missing sources with their base URLs.

    Args:
        session: Database session

    Returns:
        Mapping of source name to source ID
    """
    source_map: Dict[str, int] = {}

    for name, base_url in SOURCE_BASE_URLS.items():
        source = get_or_create_source(session, name, base_url)
        source_map[name] = source.id

    return source_map


async def run_single_scraper(
    source: Source,
    scraper_func: AsyncScraperFunc,
) -> Tuple[ScraperResults, Optional[str]]:
    """
    Run a single scraper with error isolation.

    Args:
        source: Source database model
        scraper_func: Async scraper function to call

    Returns:
        Tuple of (results, error_message). Error is None on success.
    """
    try:
        results = await scraper_func()
        return results, None
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"Scraper failed for {source.name}: {error_msg}")
        return [], error_msg


async def run_crawl_async(
    session: Session,
    state_prepared: bool = False,
    trigger: str = "manual"
) -> CrawlResult:
    """
    Run complete crawl asynchronously: scrape all active sources, match, and save.

    This is the async version for use with async contexts.

    Args:
        session: Database session
        state_prepared: If True, assumes prepare_crawl_state() was already called.
                       This avoids race conditions when starting crawl in background.
        trigger: 'manual' or 'cronjob' - how the crawl was initiated

    Returns:
        CrawlResult with statistics about the crawl

    Raises:
        RuntimeError: If a crawl is already running (and state not prepared)
    """
    global _crawl_state

    # If state was not prepared by caller, set it up now
    if not state_prepared:
        # Check if already running
        if _crawl_state.is_running:
            raise RuntimeError("A crawl is already running")

        # Mark as running, reset cancel flag and clear log
        _crawl_state.is_running = True
        _crawl_state.cancel_requested = False
        _crawl_state.current_source = None
        clear_crawl_log()

    start_time = time.time()
    result = CrawlResult()
    result.started_at = datetime.now(timezone.utc)

    # Create crawl log entry
    crawl_log = create_crawl_log(session, trigger=trigger)

    logger.info("Starting crawl run")
    add_crawl_log("Crawl gestartet")

    try:
        # Ensure all sources exist in database and get source_id mapping
        source_map = ensure_sources_exist(session)

        # Get active sources
        active_sources = get_active_sources(session)
        if not active_sources:
            logger.warning("No active sources found")
            add_crawl_log("Keine aktiven Quellen gefunden")
            result.duration_seconds = time.time() - start_time
            result.completed_at = datetime.now(timezone.utc)
            _crawl_state.last_result = result
            # Update crawl log with failed status (no sources)
            update_crawl_log(
                session, crawl_log, status="failed",
                duration_seconds=result.duration_seconds,
            )
            return result

        logger.info(f"Found {len(active_sources)} active sources")
        add_crawl_log(f"{len(active_sources)} aktive Quellen gefunden")

        # Collect all listings from all scrapers
        all_listings: ScraperResults = []

        for source in active_sources:
            # Check for cancellation before starting next source
            if _crawl_state.cancel_requested:
                logger.info("Crawl cancelled by user")
                result.duration_seconds = time.time() - start_time
                result.completed_at = datetime.now(timezone.utc)
                _crawl_state.last_result = result
                _log_crawl_summary(result)
                # Update crawl log with cancelled status
                update_crawl_log(
                    session, crawl_log, status="cancelled",
                    sources_attempted=result.sources_attempted,
                    sources_succeeded=result.sources_succeeded,
                    sources_failed=result.sources_failed,
                    total_listings=result.total_listings,
                    new_matches=result.new_matches,
                    duplicate_matches=result.duplicate_matches,
                    duration_seconds=result.duration_seconds,
                )
                return result

            result.sources_attempted += 1

            # Check if scraper exists for this source
            scraper_func = SCRAPER_REGISTRY.get(source.name)
            if not scraper_func:
                logger.warning(f"No scraper registered for source: {source.name}")
                result.sources_failed += 1
                result.failed_sources.append(source.name)
                source.last_error = "No scraper registered"
                continue

            logger.info(f"Running scraper for {source.name}")
            _crawl_state.current_source = source.name
            add_crawl_log(f"Starte {source.name}...")

            # Run scraper with error isolation (await async scraper)
            listings, error = await run_single_scraper(source, scraper_func)

            if error:
                result.sources_failed += 1
                result.failed_sources.append(source.name)
                source.last_error = error
                add_crawl_log(f"✗ {source.name}: Fehler - {error[:50]}")
            else:
                result.sources_succeeded += 1
                result.total_listings += len(listings)
                all_listings.extend(listings)
                source.last_crawl_at = datetime.now(timezone.utc)
                source.last_error = None
                logger.info(f"Scraped {len(listings)} listings from {source.name}")
                add_crawl_log(f"✓ {source.name}: {len(listings)} Inserate gefunden")

        # Commit source updates
        session.commit()

        # Get active search terms for matching
        search_terms = get_active_search_terms(session)
        if not search_terms:
            logger.warning("No active search terms found, skipping matching")
            add_crawl_log("Keine Suchbegriffe - Matching übersprungen")
            result.duration_seconds = time.time() - start_time
            result.completed_at = datetime.now(timezone.utc)
            _crawl_state.last_result = result
            _log_crawl_summary(result)
            # Update crawl log - partial success (scraped but no matching)
            update_crawl_log(
                session, crawl_log, status="partial",
                sources_attempted=result.sources_attempted,
                sources_succeeded=result.sources_succeeded,
                sources_failed=result.sources_failed,
                total_listings=result.total_listings,
                duration_seconds=result.duration_seconds,
            )
            return result

        # Convert search terms to dict format for matching
        term_dicts = [search_term_to_dict(term) for term in search_terms]

        logger.info(
            f"Matching {len(all_listings)} listings against {len(term_dicts)} search terms"
        )
        add_crawl_log(f"Vergleiche {len(all_listings)} Inserate mit {len(term_dicts)} Suchbegriffen...")

        # Find matches (exclude terms are only applied visually in dashboard, not during crawl)
        match_results = find_matches(all_listings, term_dicts)
        logger.info(f"Found {len(match_results)} potential matches")
        add_crawl_log(f"→ {len(match_results)} potentielle Treffer gefunden")

        # Save matches with deduplication
        if match_results:
            add_crawl_log("Speichere Treffer...")
            new_count, dup_count = save_matches(session, match_results, source_map)
            result.new_matches = new_count
            result.duplicate_matches = dup_count
            add_crawl_log(f"✓ {new_count} neue Treffer, {dup_count} Duplikate übersprungen")

        result.duration_seconds = time.time() - start_time
        result.completed_at = datetime.now(timezone.utc)

        # Update global state
        _crawl_state.last_result = result

        _log_crawl_summary(result)
        add_crawl_log(f"Crawl abgeschlossen in {result.duration_seconds:.1f}s")

        # Determine final status
        if result.sources_failed > 0 and result.sources_succeeded > 0:
            status = "partial"
        elif result.sources_failed > 0:
            status = "failed"
        else:
            status = "success"

        # Update crawl log with final results
        update_crawl_log(
            session, crawl_log, status=status,
            sources_attempted=result.sources_attempted,
            sources_succeeded=result.sources_succeeded,
            sources_failed=result.sources_failed,
            total_listings=result.total_listings,
            new_matches=result.new_matches,
            duplicate_matches=result.duplicate_matches,
            duration_seconds=result.duration_seconds,
        )

        return result

    except Exception as e:
        logger.error(f"Crawl failed with exception: {e}")
        add_crawl_log(f"✗ FEHLER: {str(e)}")
        # Update crawl log with failed status
        result.duration_seconds = time.time() - start_time
        update_crawl_log(
            session, crawl_log, status="failed",
            sources_attempted=result.sources_attempted,
            sources_succeeded=result.sources_succeeded,
            sources_failed=result.sources_failed,
            total_listings=result.total_listings,
            duration_seconds=result.duration_seconds,
        )
        raise

    finally:
        # Always reset running state
        _crawl_state.is_running = False
        _crawl_state.cancel_requested = False
        _crawl_state.current_source = None


def run_crawl(session: Session) -> CrawlResult:
    """
    Run complete crawl: scrape all active sources, match, and save.

    This is the main entry point for crawling. It:
    1. Gets active sources from database
    2. Runs each scraper sequentially
    3. Handles failures gracefully
    4. Matches all results against search terms
    5. Saves matches with deduplication
    6. Logs summary

    This is a synchronous wrapper around run_crawl_async for use in
    non-async contexts (like CLI commands).

    Args:
        session: Database session

    Returns:
        CrawlResult with statistics about the crawl
    """
    return asyncio.run(run_crawl_async(session))


def _log_crawl_summary(result: CrawlResult) -> None:
    """Log a summary of the crawl results."""
    logger.info("=" * 60)
    logger.info("CRAWL SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Sources attempted: {result.sources_attempted}")
    logger.info(f"Sources succeeded: {result.sources_succeeded}")
    logger.info(f"Sources failed: {result.sources_failed}")

    if result.failed_sources:
        logger.info(f"Failed sources: {', '.join(result.failed_sources)}")

    logger.info(f"Total listings scraped: {result.total_listings}")
    logger.info(f"New matches saved: {result.new_matches}")
    logger.info(f"Duplicate matches skipped: {result.duplicate_matches}")
    logger.info(f"Duration: {result.duration_seconds:.1f} seconds")
    logger.info("=" * 60)
