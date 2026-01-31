"""
waffen-joray.ch Scraper

Scrapes firearms listings from waffen-joray.ch using Joomla search.
The website uses VirtueMart e-commerce with Joomla's built-in search component.

Search URL: https://waffen-joray.ch/component/search/?searchword=<term>&limit=100
"""
import re
from typing import List, Optional

from bs4 import BeautifulSoup

from backend.scrapers.base import (
    ScraperResult,
    ScraperResults,
    create_http_client,
    delay_between_requests,
    make_absolute_url,
)
from backend.utils.logging import get_logger

logger = get_logger(__name__)

BASE_URL = "https://waffen-joray.ch"
SEARCH_URL = f"{BASE_URL}/component/search/"
SOURCE_NAME = "waffen-joray.ch"
MAX_RESULTS = 100  # Max results per search term


async def scrape_waffenjoray(search_terms: Optional[List[str]] = None) -> ScraperResults:
    """
    Scrape listings from waffen-joray.ch using Joomla search.

    The search returns product listings with title, link, category, and description.
    Price and image are not available in search results.

    Args:
        search_terms: Optional list of search terms. If None, fetches from database.

    Returns:
        List of ScraperResult dicts with title, link, source.
        Returns empty list on any error.
    """
    from backend.services.crawler import add_crawl_log
    from urllib.parse import quote_plus

    # If no search terms provided, get them from the database
    if search_terms is None:
        from backend.database import SessionLocal
        from backend.database.crud import get_active_search_terms
        with SessionLocal() as session:
            db_terms = get_active_search_terms(session)
            search_terms = [t.term for t in db_terms]

    if not search_terms:
        logger.warning(f"{SOURCE_NAME} - No search terms to search for")
        return []

    results: ScraperResults = []
    seen_links = set()  # Deduplicate results across searches

    try:
        from backend.services.crawler import is_cancel_requested

        async with create_http_client() as client:
            for term in search_terms:
                # Check for cancellation between search terms
                if is_cancel_requested():
                    logger.info(f"{SOURCE_NAME} - Cancelled by user")
                    return results
                add_crawl_log(f"  → Suche: '{term}'")

                # Construct search URL
                encoded_term = quote_plus(term)
                url = f"{SEARCH_URL}?searchword={encoded_term}&limit={MAX_RESULTS}"

                try:
                    response = await client.get(url)
                    response.raise_for_status()

                    # Parse HTML
                    soup = BeautifulSoup(response.text, "html.parser")

                    # Find all search results
                    # Joomla search results are typically in <dl class="search-results"> or similar
                    # Each result has <dt> with link and <dd> with description
                    term_results = 0

                    # Try multiple result container patterns
                    # Pattern 1: dl/dt structure
                    results_dl = soup.select("dl.search-results dt, .search-results dt")
                    for dt in results_dl:
                        result = _parse_search_result_dt(dt)
                        if result and result["link"] not in seen_links:
                            seen_links.add(result["link"])
                            results.append(result)
                            term_results += 1

                    # Pattern 2: Direct links in result containers
                    if term_results == 0:
                        # Try to find result items in other structures
                        result_items = soup.select(".result, .search-result, article")
                        for item in result_items:
                            result = _parse_search_result_item(item)
                            if result and result["link"] not in seen_links:
                                seen_links.add(result["link"])
                                results.append(result)
                                term_results += 1

                    # Pattern 3: Look for h3 elements with product links (common Joomla pattern)
                    if term_results == 0:
                        h3_links = soup.select("h3 a[href*='/waffen/'], h3 a[href*='-detail']")
                        for link in h3_links:
                            result = _parse_h3_link(link)
                            if result and result["link"] not in seen_links:
                                seen_links.add(result["link"])
                                results.append(result)
                                term_results += 1

                    # Pattern 4: Any link that looks like a product detail page
                    if term_results == 0:
                        product_links = soup.select("a[href*='-detail']")
                        for link in product_links:
                            result = _parse_product_link(link)
                            if result and result["link"] not in seen_links:
                                seen_links.add(result["link"])
                                results.append(result)
                                term_results += 1

                    if term_results > 0:
                        add_crawl_log(f"    {term_results} Produkte gefunden")
                    else:
                        add_crawl_log(f"    Keine Ergebnisse für '{term}'")

                    logger.debug(f"{SOURCE_NAME} - Search '{term}': found {term_results} results")

                except Exception as e:
                    logger.warning(f"{SOURCE_NAME} - Search failed for '{term}': {e}")
                    add_crawl_log(f"    Fehler bei '{term}': {e}")
                    continue

                # Delay between search terms
                await delay_between_requests()

            logger.info(f"{SOURCE_NAME} - Scraped {len(results)} unique listings total")

    except Exception as e:
        logger.error(f"{SOURCE_NAME} - Failed: {e}")
        add_crawl_log(f"  Fehler: {e}")
        return []

    return results


def _parse_search_result_dt(dt) -> Optional[ScraperResult]:
    """Parse a search result from <dt> element."""
    link_elem = dt.select_one("a")
    if not link_elem:
        return None

    href = link_elem.get("href", "")
    if not href:
        return None

    title = link_elem.get_text(strip=True)
    if not title:
        return None

    return ScraperResult(
        title=title,
        price=None,
        image_url=None,
        link=make_absolute_url(BASE_URL, href),
        source=SOURCE_NAME
    )


def _parse_search_result_item(item) -> Optional[ScraperResult]:
    """Parse a search result from a generic result container."""
    # Try to find title link
    link_elem = item.select_one("a[href*='/waffen/'], a[href*='-detail'], h3 a, h2 a, .title a")
    if not link_elem:
        return None

    href = link_elem.get("href", "")
    if not href:
        return None

    title = link_elem.get_text(strip=True)
    if not title:
        return None

    return ScraperResult(
        title=title,
        price=None,
        image_url=None,
        link=make_absolute_url(BASE_URL, href),
        source=SOURCE_NAME
    )


def _parse_h3_link(link) -> Optional[ScraperResult]:
    """Parse a product link from h3 element."""
    href = link.get("href", "")
    if not href:
        return None

    title = link.get_text(strip=True)
    if not title:
        return None

    # Skip non-product links
    if not _is_product_link(href):
        return None

    return ScraperResult(
        title=title,
        price=None,
        image_url=None,
        link=make_absolute_url(BASE_URL, href),
        source=SOURCE_NAME
    )


def _parse_product_link(link) -> Optional[ScraperResult]:
    """Parse any link that looks like a product detail page."""
    href = link.get("href", "")
    if not href:
        return None

    # Must end with -detail or be a product page
    if not _is_product_link(href):
        return None

    title = link.get_text(strip=True)
    if not title or len(title) < 3:
        return None

    # Skip navigation/category links
    skip_words = ["mehr", "weiter", "zurück", "kategorie", "alle"]
    if any(word in title.lower() for word in skip_words):
        return None

    return ScraperResult(
        title=title,
        price=None,
        image_url=None,
        link=make_absolute_url(BASE_URL, href),
        source=SOURCE_NAME
    )


def _is_product_link(href: str) -> bool:
    """Check if a URL looks like a product detail page."""
    href_lower = href.lower()

    # Must contain -detail or be in a product category
    if "-detail" in href_lower:
        return True

    # Check for VirtueMart product patterns
    if "/waffen/" in href_lower and re.search(r'/\d+/', href):
        return True

    return False
