"""
Database CRUD Operations for Gebrauchtwaffen Aggregator.

Provides functions for:
- Source management (get, create)
- Search term queries
- Match persistence with deduplication
- App settings and new match detection
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.database.models import AppSettings, ExcludeTerm, Match, SearchTerm, Source
from backend.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Source Operations
# =============================================================================


def get_source_by_name(session: Session, name: str) -> Optional[Source]:
    """
    Get a source by its name.

    Args:
        session: Database session
        name: Source name (e.g., "waffenboerse.ch")

    Returns:
        Source if found, None otherwise
    """
    return session.query(Source).filter(Source.name == name).first()


def get_or_create_source(session: Session, name: str, base_url: str) -> Source:
    """
    Get existing source by name or create a new one.

    Args:
        session: Database session
        name: Source name (e.g., "waffenboerse.ch")
        base_url: Base URL for the source

    Returns:
        Existing or newly created Source
    """
    source = get_source_by_name(session, name)
    if source:
        return source

    # Get the next sort_order value
    max_order = session.query(Source).count()
    source = Source(name=name, base_url=base_url, is_active=True, sort_order=max_order)
    session.add(source)
    session.commit()
    session.refresh(source)

    logger.info(f"Created new source: {name}")
    return source


def get_all_sources(session: Session) -> list[Source]:
    """
    Get all sources.

    Args:
        session: Database session

    Returns:
        List of all Source records
    """
    return session.query(Source).all()


def get_active_sources(session: Session) -> list[Source]:
    """
    Get all active sources sorted by sort_order.

    Args:
        session: Database session

    Returns:
        List of active Source records sorted by sort_order
    """
    return session.query(Source).filter(Source.is_active == True).order_by(Source.sort_order).all()


def get_all_sources_sorted(session: Session) -> list[Source]:
    """
    Get all sources sorted by sort_order.

    Args:
        session: Database session

    Returns:
        List of all Source records sorted by sort_order
    """
    return session.query(Source).order_by(Source.sort_order).all()


def get_source_by_id(session: Session, source_id: int) -> Optional[Source]:
    """
    Get a source by ID.

    Args:
        session: Database session
        source_id: Source ID

    Returns:
        Source if found, None otherwise
    """
    return session.query(Source).filter(Source.id == source_id).first()


def toggle_source_active(session: Session, source_id: int) -> Optional[Source]:
    """
    Toggle a source's active state.

    Args:
        session: Database session
        source_id: Source ID

    Returns:
        Updated Source, or None if not found
    """
    source = get_source_by_id(session, source_id)
    if not source:
        return None

    source.is_active = not source.is_active
    session.commit()
    session.refresh(source)

    status = "activated" if source.is_active else "deactivated"
    logger.info(f"Source '{source.name}' {status}")
    return source


def update_source_last_crawl(
    session: Session,
    source_id: int,
    error: Optional[str] = None
) -> Optional[Source]:
    """
    Update a source's last crawl timestamp and optionally set error.

    Args:
        session: Database session
        source_id: Source ID
        error: Error message if crawl failed, None if successful

    Returns:
        Updated Source, or None if not found
    """
    source = get_source_by_id(session, source_id)
    if not source:
        return None

    source.last_crawl_at = datetime.now(timezone.utc)
    source.last_error = error
    session.commit()
    session.refresh(source)

    return source


def clear_source_error(session: Session, source_id: int) -> Optional[Source]:
    """
    Clear a source's error state.

    Args:
        session: Database session
        source_id: Source ID

    Returns:
        Updated Source, or None if not found
    """
    source = get_source_by_id(session, source_id)
    if not source:
        return None

    source.last_error = None
    session.commit()
    session.refresh(source)

    logger.info(f"Cleared error for source '{source.name}'")
    return source


def move_source_up(session: Session, source_id: int) -> list[Source]:
    """
    Move a source up in the sort order (swap with previous source).

    Args:
        session: Database session
        source_id: Source ID to move up

    Returns:
        Updated list of all sources sorted by sort_order
    """
    source = get_source_by_id(session, source_id)
    if not source:
        return get_all_sources_sorted(session)

    # Find the source with the next lower sort_order
    prev_source = session.query(Source).filter(
        Source.sort_order < source.sort_order
    ).order_by(Source.sort_order.desc()).first()

    if prev_source:
        # Swap sort_order values
        source.sort_order, prev_source.sort_order = prev_source.sort_order, source.sort_order
        session.commit()
        logger.info(f"Moved source '{source.name}' up")

    return get_all_sources_sorted(session)


def move_source_down(session: Session, source_id: int) -> list[Source]:
    """
    Move a source down in the sort order (swap with next source).

    Args:
        session: Database session
        source_id: Source ID to move down

    Returns:
        Updated list of all sources sorted by sort_order
    """
    source = get_source_by_id(session, source_id)
    if not source:
        return get_all_sources_sorted(session)

    # Find the source with the next higher sort_order
    next_source = session.query(Source).filter(
        Source.sort_order > source.sort_order
    ).order_by(Source.sort_order.asc()).first()

    if next_source:
        # Swap sort_order values
        source.sort_order, next_source.sort_order = next_source.sort_order, source.sort_order
        session.commit()
        logger.info(f"Moved source '{source.name}' down")

    return get_all_sources_sorted(session)


# =============================================================================
# Search Term Operations
# =============================================================================


def get_active_search_terms(session: Session) -> list[SearchTerm]:
    """
    Get all active search terms for matching, ordered by sort_order.

    Args:
        session: Database session

    Returns:
        List of active SearchTerm records ordered by sort_order
    """
    return session.query(SearchTerm).filter(
        SearchTerm.is_active == True
    ).order_by(SearchTerm.sort_order).all()


def get_all_search_terms(session: Session) -> list[SearchTerm]:
    """
    Get all search terms (active and inactive), ordered by sort_order.

    Args:
        session: Database session

    Returns:
        List of all SearchTerm records ordered by sort_order
    """
    return session.query(SearchTerm).order_by(SearchTerm.sort_order).all()


def search_term_to_dict(term: SearchTerm) -> dict:
    """
    Convert SearchTerm model to dict for matching interface.

    The matching module expects dicts with specific keys.

    Args:
        term: SearchTerm model instance

    Returns:
        Dict with id, term, match_type, is_active keys
    """
    return {
        "id": term.id,
        "term": term.term,
        "match_type": term.match_type,
        "is_active": term.is_active,
    }


def get_all_search_terms_sorted(session: Session) -> list[SearchTerm]:
    """
    Get all search terms sorted alphabetically by term.

    Args:
        session: Database session

    Returns:
        List of all SearchTerm records sorted alphabetically
    """
    return session.query(SearchTerm).order_by(SearchTerm.term).all()


def get_search_term_by_id(session: Session, term_id: int) -> Optional[SearchTerm]:
    """
    Get a search term by ID.

    Args:
        session: Database session
        term_id: Search term ID

    Returns:
        SearchTerm if found, None otherwise
    """
    return session.query(SearchTerm).filter(SearchTerm.id == term_id).first()


def get_search_term_by_term(session: Session, term: str) -> Optional[SearchTerm]:
    """
    Get a search term by its text (case-insensitive).

    Args:
        session: Database session
        term: Search term text

    Returns:
        SearchTerm if found, None otherwise
    """
    return session.query(SearchTerm).filter(
        SearchTerm.term.ilike(term)
    ).first()


def create_search_term(
    session: Session,
    term: str,
    match_type: str = "exact",
    is_active: bool = True
) -> SearchTerm:
    """
    Create a new search term.

    Args:
        session: Database session
        term: Search term text
        match_type: "exact" or "similar"
        is_active: Whether term is active

    Returns:
        Newly created SearchTerm
    """
    # Get the highest sort_order and add 1
    max_order = session.query(SearchTerm).count()
    search_term = SearchTerm(
        term=term,
        match_type=match_type,
        is_active=is_active,
        sort_order=max_order
    )
    session.add(search_term)
    session.commit()
    session.refresh(search_term)
    return search_term


def delete_search_term(session: Session, term_id: int) -> bool:
    """
    Delete a search term by ID.

    Note: Associated matches remain in the database (orphaned) per requirements.
    The cascade delete on the relationship will handle cleanup.

    Args:
        session: Database session
        term_id: Search term ID

    Returns:
        True if deleted, False if not found
    """
    term = get_search_term_by_id(session, term_id)
    if not term:
        return False

    session.delete(term)
    session.commit()
    logger.info(f"Deleted search term: {term.term}")
    return True


def update_search_term_match_type(
    session: Session,
    term_id: int,
    match_type: str
) -> Optional[SearchTerm]:
    """
    Update a search term's match type.

    Args:
        session: Database session
        term_id: Search term ID
        match_type: New match type ("exact" or "similar")

    Returns:
        Updated SearchTerm, or None if not found
    """
    if match_type not in ("exact", "similar"):
        raise ValueError(f"Invalid match_type: {match_type}")

    term = get_search_term_by_id(session, term_id)
    if not term:
        return None

    term.match_type = match_type
    session.commit()
    session.refresh(term)

    logger.info(f"Updated search term '{term.term}' match_type to '{match_type}'")
    return term


def move_search_term_up(session: Session, term_id: int) -> Optional[SearchTerm]:
    """
    Move a search term up in sort order (decrease sort_order).

    Args:
        session: Database session
        term_id: Search term ID

    Returns:
        Updated SearchTerm, or None if not found or already at top
    """
    term = get_search_term_by_id(session, term_id)
    if not term:
        return None

    # Find the term above this one (with lower sort_order)
    term_above = session.query(SearchTerm).filter(
        SearchTerm.sort_order < term.sort_order
    ).order_by(SearchTerm.sort_order.desc()).first()

    if not term_above:
        # Already at top
        return term

    # Swap sort_orders
    term.sort_order, term_above.sort_order = term_above.sort_order, term.sort_order
    session.commit()
    session.refresh(term)

    logger.info(f"Moved search term '{term.term}' up")
    return term


def move_search_term_down(session: Session, term_id: int) -> Optional[SearchTerm]:
    """
    Move a search term down in sort order (increase sort_order).

    Args:
        session: Database session
        term_id: Search term ID

    Returns:
        Updated SearchTerm, or None if not found or already at bottom
    """
    term = get_search_term_by_id(session, term_id)
    if not term:
        return None

    # Find the term below this one (with higher sort_order)
    term_below = session.query(SearchTerm).filter(
        SearchTerm.sort_order > term.sort_order
    ).order_by(SearchTerm.sort_order.asc()).first()

    if not term_below:
        # Already at bottom
        return term

    # Swap sort_orders
    term.sort_order, term_below.sort_order = term_below.sort_order, term.sort_order
    session.commit()
    session.refresh(term)

    logger.info(f"Moved search term '{term.term}' down")
    return term


# =============================================================================
# Exclude Term Operations
# =============================================================================


def get_all_exclude_terms(session: Session) -> list[ExcludeTerm]:
    """
    Get all exclude terms (active and inactive).

    Args:
        session: Database session

    Returns:
        List of all ExcludeTerm records
    """
    return session.query(ExcludeTerm).all()


def get_all_exclude_terms_sorted(session: Session) -> list[ExcludeTerm]:
    """
    Get all exclude terms sorted alphabetically by term.

    Args:
        session: Database session

    Returns:
        List of all ExcludeTerm records sorted alphabetically
    """
    return session.query(ExcludeTerm).order_by(ExcludeTerm.term).all()


def get_active_exclude_terms(session: Session) -> list[ExcludeTerm]:
    """
    Get all active exclude terms.

    Args:
        session: Database session

    Returns:
        List of active ExcludeTerm records
    """
    return session.query(ExcludeTerm).filter(ExcludeTerm.is_active == True).all()


def get_exclude_term_by_id(session: Session, term_id: int) -> Optional[ExcludeTerm]:
    """
    Get an exclude term by ID.

    Args:
        session: Database session
        term_id: Exclude term ID

    Returns:
        ExcludeTerm if found, None otherwise
    """
    return session.query(ExcludeTerm).filter(ExcludeTerm.id == term_id).first()


def get_exclude_term_by_term(session: Session, term: str) -> Optional[ExcludeTerm]:
    """
    Get an exclude term by its text (case-insensitive).

    Args:
        session: Database session
        term: Exclude term text

    Returns:
        ExcludeTerm if found, None otherwise
    """
    return session.query(ExcludeTerm).filter(
        ExcludeTerm.term.ilike(term)
    ).first()


def create_exclude_term(
    session: Session,
    term: str,
    is_active: bool = True
) -> ExcludeTerm:
    """
    Create a new exclude term.

    Args:
        session: Database session
        term: Exclude term text
        is_active: Whether term is active

    Returns:
        Newly created ExcludeTerm
    """
    exclude_term = ExcludeTerm(term=term, is_active=is_active)
    session.add(exclude_term)
    session.commit()
    session.refresh(exclude_term)
    logger.info(f"Created exclude term: {term}")
    return exclude_term


# Default exclude terms to create on first startup only
DEFAULT_EXCLUDE_TERMS = ["CO2", "Airsoft", "Softair"]


def ensure_default_exclude_terms(session: Session) -> list[ExcludeTerm]:
    """
    Create default exclude terms on first startup only.

    Only creates default terms if the exclude_terms table is completely empty.
    This ensures user modifications (additions, deletions) are preserved
    across server restarts.

    Args:
        session: Database session

    Returns:
        List of all exclude terms
    """
    # Only create defaults if table is empty (first run)
    existing_count = session.query(ExcludeTerm).count()
    if existing_count > 0:
        logger.debug("Exclude terms already exist, skipping defaults")
        return get_all_exclude_terms_sorted(session)

    # First run - create default exclude terms
    for term in DEFAULT_EXCLUDE_TERMS:
        create_exclude_term(session, term)

    logger.info(f"Created {len(DEFAULT_EXCLUDE_TERMS)} default exclude terms (first run)")
    return get_all_exclude_terms_sorted(session)


def delete_exclude_term(session: Session, term_id: int) -> bool:
    """
    Delete an exclude term by ID.

    Args:
        session: Database session
        term_id: Exclude term ID

    Returns:
        True if deleted, False if not found
    """
    term = get_exclude_term_by_id(session, term_id)
    if not term:
        return False

    session.delete(term)
    session.commit()
    logger.info(f"Deleted exclude term: {term.term}")
    return True


def toggle_exclude_term_active(session: Session, term_id: int) -> Optional[ExcludeTerm]:
    """
    Toggle an exclude term's active state.

    Args:
        session: Database session
        term_id: Exclude term ID

    Returns:
        Updated ExcludeTerm, or None if not found
    """
    term = get_exclude_term_by_id(session, term_id)
    if not term:
        return None

    term.is_active = not term.is_active
    session.commit()
    session.refresh(term)

    status = "activated" if term.is_active else "deactivated"
    logger.info(f"Exclude term '{term.term}' {status}")
    return term


# =============================================================================
# Match Operations
# =============================================================================


def get_match_by_url_and_term(
    session: Session,
    url: str,
    search_term_id: int
) -> Optional[Match]:
    """
    Check if a match already exists for deduplication.

    A match is unique by (url, search_term_id). The same listing can
    match different search terms, but we don't want duplicates for
    the same listing + term combination.

    Args:
        session: Database session
        url: Listing URL
        search_term_id: Search term ID

    Returns:
        Match if found, None otherwise
    """
    return session.query(Match).filter(
        Match.url == url,
        Match.search_term_id == search_term_id
    ).first()


def save_match(
    session: Session,
    match_result: dict,
    source_id: int
) -> Optional[Match]:
    """
    Save a single match to the database.

    Handles deduplication: if a match with the same URL and search_term_id
    already exists, returns None without creating a duplicate.

    Args:
        session: Database session
        match_result: MatchResult dict from matching.py with keys:
            - listing: dict with title, price, image_url, link, source
            - search_term_id: int
            - search_term: str
            - match_type: str
        source_id: Source database ID

    Returns:
        Newly created Match, or None if duplicate
    """
    listing = match_result.get("listing", {})
    search_term_id = match_result.get("search_term_id")
    url = listing.get("link", "")

    if not url or not search_term_id:
        logger.warning("Invalid match_result: missing url or search_term_id")
        return None

    # Check for duplicate
    existing = get_match_by_url_and_term(session, url, search_term_id)
    if existing:
        return None

    # Convert price to string for storage (model uses String field)
    price = listing.get("price")
    price_str = str(price) if price is not None else None

    # Create new match
    match = Match(
        source_id=source_id,
        search_term_id=search_term_id,
        title=listing.get("title", ""),
        price=price_str,
        url=url,
        image_url=listing.get("image_url"),
        is_new=True,  # New matches are marked as new
    )

    session.add(match)
    return match


def save_matches(
    session: Session,
    match_results: list[dict],
    source_map: dict[str, int]
) -> tuple[int, int]:
    """
    Bulk save matches to the database with deduplication.

    Args:
        session: Database session
        match_results: List of MatchResult dicts from matching.py
        source_map: Mapping of source name to source_id

    Returns:
        Tuple of (new_count, duplicate_count)
    """
    new_count = 0
    duplicate_count = 0

    for match_result in match_results:
        listing = match_result.get("listing", {})
        source_name = listing.get("source", "")

        source_id = source_map.get(source_name)
        if not source_id:
            logger.warning(f"Unknown source: {source_name}, skipping match")
            continue

        match = save_match(session, match_result, source_id)
        if match:
            new_count += 1
        else:
            duplicate_count += 1

    # Commit all new matches in one transaction
    if new_count > 0:
        session.commit()

    logger.info(f"Saved {new_count} new matches, skipped {duplicate_count} duplicates")
    return new_count, duplicate_count


def get_matches_by_search_term(
    session: Session,
    search_term_id: int
) -> list[Match]:
    """
    Get all matches for a specific search term.

    Args:
        session: Database session
        search_term_id: Search term ID

    Returns:
        List of Match records
    """
    return session.query(Match).filter(
        Match.search_term_id == search_term_id
    ).order_by(Match.created_at.desc()).all()


def get_all_matches(session: Session) -> list[Match]:
    """
    Get all matches ordered by creation date (newest first).

    Args:
        session: Database session

    Returns:
        List of all Match records
    """
    return session.query(Match).order_by(Match.created_at.desc()).all()


def get_new_matches(session: Session) -> list[Match]:
    """
    Get all matches marked as new.

    Args:
        session: Database session

    Returns:
        List of Match records where is_new=True
    """
    return session.query(Match).filter(
        Match.is_new == True
    ).order_by(Match.created_at.desc()).all()


# =============================================================================
# App Settings & New Match Detection Operations
# =============================================================================


def get_app_settings(session: Session) -> AppSettings:
    """
    Get app settings (creates default if not exists).

    The app_settings table should only have one row. This function
    retrieves it or creates a new one if it doesn't exist.

    Args:
        session: Database session

    Returns:
        AppSettings instance
    """
    settings = session.query(AppSettings).first()
    if settings:
        return settings

    # Create default settings
    settings = AppSettings(last_seen_at=None)
    session.add(settings)
    session.commit()
    session.refresh(settings)

    logger.info("Created default app settings")
    return settings


def mark_matches_as_seen(session: Session) -> int:
    """
    Mark all current matches as seen (is_new=False).

    This is called when the user views the dashboard to mark all
    existing matches as "seen". New matches arriving after this
    will have is_new=True by default.

    Args:
        session: Database session

    Returns:
        Number of matches marked as seen
    """
    # Update all matches with is_new=True to is_new=False
    count = session.query(Match).filter(
        Match.is_new == True
    ).update({Match.is_new: False})

    # Update last_seen_at timestamp
    settings = get_app_settings(session)
    settings.last_seen_at = datetime.now(timezone.utc)

    session.commit()

    if count > 0:
        logger.info(f"Marked {count} matches as seen")

    return count


def get_last_seen_at(session: Session) -> Optional[datetime]:
    """
    Get the timestamp when matches were last marked as seen.

    Args:
        session: Database session

    Returns:
        Last seen timestamp, or None if never seen
    """
    settings = get_app_settings(session)
    return settings.last_seen_at


def get_new_match_count(session: Session) -> int:
    """
    Get count of matches marked as new.

    Args:
        session: Database session

    Returns:
        Number of matches where is_new=True
    """
    return session.query(Match).filter(Match.is_new == True).count()
