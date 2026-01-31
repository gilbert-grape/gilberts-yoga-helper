"""
Scraper Base Utilities

Shared utilities for all scrapers including:
- HTTP client configuration with timeout and User-Agent
- Rate limiting with random delays
- URL utilities for converting relative URLs
- Price parsing for Swiss number formats
- Type definitions for scraper results
"""
import asyncio
import random
import re
import sys
from typing import List, Optional

if sys.version_info >= (3, 8):
    from typing import TypedDict
else:
    from typing_extensions import TypedDict
from urllib.parse import urljoin

import httpx

# Constants for HTTP requests
REQUEST_TIMEOUT = 30  # seconds
REQUEST_DELAY_MIN = 2  # seconds between requests
REQUEST_DELAY_MAX = 5  # seconds between requests


class ScraperResult(TypedDict, total=False):
    """Standard result type for all scrapers.

    Attributes:
        title: Listing title (required)
        price: Price in CHF as float, None for "Auf Anfrage" or missing
        image_url: Absolute URL to image, None if no image available
        link: Absolute URL to original listing (required)
        source: Source website name, e.g., "waffenboerse.ch" (required)
        found_by_term: Search term that found this listing (optional).
                      When set, the listing will be considered a match for this term
                      even if the term doesn't appear in the title.
    """
    title: str
    price: Optional[float]
    image_url: Optional[str]
    link: str
    source: str
    found_by_term: Optional[str]


# Type alias for list of scraper results
ScraperResults = List[ScraperResult]


def get_user_agent() -> str:
    """Return a proper User-Agent string for scraper requests.

    Returns:
        User-Agent string identifying the scraper.
    """
    return "Mozilla/5.0 (compatible; YogaHelper/1.0)"


def create_http_client() -> httpx.AsyncClient:
    """Create a configured async HTTP client for scraping.

    The client is configured with:
    - 30 second timeout for all operations
    - Proper User-Agent header
    - Redirect following enabled
    - SSL verification disabled (required for some sites)

    Returns:
        Configured httpx.AsyncClient instance.

    Note:
        Always use as context manager: `async with create_http_client() as client:`
    """
    return httpx.AsyncClient(
        timeout=httpx.Timeout(REQUEST_TIMEOUT),
        headers={"User-Agent": get_user_agent()},
        follow_redirects=True,
        verify=False
    )


async def delay_between_requests() -> None:
    """Wait a random delay between requests to avoid rate limiting.

    Waits between REQUEST_DELAY_MIN and REQUEST_DELAY_MAX seconds.
    Uses asyncio.sleep for non-blocking async delay.
    """
    delay = random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)
    await asyncio.sleep(delay)


def make_absolute_url(base_url: str, relative_url: str) -> str:
    """Convert a relative URL to an absolute URL.

    Args:
        base_url: The base URL to resolve against.
        relative_url: The relative (or absolute) URL to convert.

    Returns:
        Absolute URL string.

    Examples:
        >>> make_absolute_url("https://example.ch/listings/", "../images/photo.jpg")
        'https://example.ch/images/photo.jpg'
        >>> make_absolute_url("https://example.ch/", "https://cdn.example.ch/img.jpg")
        'https://cdn.example.ch/img.jpg'
    """
    return urljoin(base_url, relative_url)


def parse_price(price_str: Optional[str]) -> Optional[float]:
    """Extract numeric price from a price string.

    Handles Swiss number formats with apostrophe as thousands separator
    and both comma and dot as decimal separators. Also handles dot as
    thousands separator (e.g., "1.550CHF" = 1550).

    Args:
        price_str: Price string like "CHF 1'234.50" or "1'234,50 CHF".
                   Can be None or empty.

    Returns:
        Price as float, or None for:
        - Empty/None input
        - "Auf Anfrage" or similar strings
        - Unparseable strings

    Examples:
        >>> parse_price("CHF 1'234.50")
        1234.5
        >>> parse_price("1'234,50 CHF")
        1234.5
        >>> parse_price("1.550CHF")
        1550.0
        >>> parse_price("Auf Anfrage")
        None
        >>> parse_price("")
        None
    """
    if not price_str:
        return None

    # Check for "Auf Anfrage" or similar
    if "anfrage" in price_str.lower():
        return None

    # Remove currency symbols, spaces, and non-numeric characters except ., and '
    cleaned = re.sub(r"[^\d.,']", "", price_str)

    # Remove Swiss thousands separator (apostrophe)
    cleaned = cleaned.replace("'", "")

    # Handle comma as decimal separator (European format)
    # If both . and , are present, the last one is likely decimal separator
    if "," in cleaned and "." in cleaned:
        # Swiss: 1.234,50 -> 1234.50
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        # Single comma - replace with dot for float parsing
        cleaned = cleaned.replace(",", ".")
    elif "." in cleaned:
        # Single dot - check if it's a thousands separator
        # Pattern: dot followed by exactly 3 digits at end = thousands separator
        # e.g., "1.550" = 1550, "2.500" = 2500
        # But "1.50" or "1.5" = decimal
        match = re.match(r"^(\d+)\.(\d{3})$", cleaned)
        if match:
            # Dot is thousands separator (e.g., "1.550" -> "1550")
            cleaned = cleaned.replace(".", "")

    try:
        return float(cleaned)
    except ValueError:
        return None
