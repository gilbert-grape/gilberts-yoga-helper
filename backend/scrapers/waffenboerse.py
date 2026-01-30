"""
waffenboerse.ch Scraper

Scrapes used firearms listings from waffenboerse.ch
"""
import re
from typing import List, Optional

from bs4 import BeautifulSoup, Tag

from backend.scrapers.base import (
    ScraperResult,
    ScraperResults,
    create_http_client,
    delay_between_requests,
    make_absolute_url,
    parse_price,
)
from backend.utils.logging import get_logger

logger = get_logger(__name__)

BASE_URL = "https://www.waffenboerse.ch"
# Site uses search-based scraping - search for each term directly
# This is more efficient than trying to paginate through infinite scroll
SEARCH_URL = f"{BASE_URL}/de/search/Section1.htm"
SOURCE_NAME = "waffenboerse.ch"
MAX_PAGES = 5  # Max pages per search term


async def scrape_waffenboerse(search_terms: Optional[List[str]] = None) -> ScraperResults:
    """
    Scrape listings from waffenboerse.ch using search.

    This scraper uses the site's search functionality to find relevant listings.
    If no search_terms are provided, it will fetch them from the database.

    Args:
        search_terms: Optional list of search terms. If None, fetches from database.

    Returns:
        List of ScraperResult dicts with title, price, image_url, link, source.
        Returns empty list on any error.
    """
    # Import here to avoid circular dependency
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
        async with create_http_client() as client:
            for term in search_terms:
                add_crawl_log(f"  → Suche: '{term}'")

                page = 1
                while page <= MAX_PAGES:
                    # Construct search URL with query parameter
                    encoded_term = quote_plus(term)
                    url = f"{SEARCH_URL}?query={encoded_term}"
                    if page > 1:
                        url += f"&page={page}"
                    add_crawl_log(f"    Seite {page}...")

                    response = await client.get(url)
                    response.raise_for_status()

                    # Parse HTML
                    soup = BeautifulSoup(response.text, "lxml")

                    # Find all listing items
                    listings = soup.select("article.article-list-item, .article-list-item")

                    if not listings:
                        if page == 1:
                            add_crawl_log(f"    Keine Ergebnisse für '{term}'")
                        break

                    page_results = 0
                    for listing in listings:
                        try:
                            result = _parse_listing(listing)
                            if result and result["link"] not in seen_links:
                                seen_links.add(result["link"])
                                results.append(result)
                                page_results += 1
                        except Exception as e:
                            logger.warning(f"{SOURCE_NAME} - Failed to parse listing: {e}")
                            continue

                    logger.debug(f"{SOURCE_NAME} - Search '{term}' page {page}: found {page_results} new listings")

                    # Check if there's a next page
                    if not _has_next_page(soup, page) or page_results == 0:
                        break

                    page += 1
                    if page <= MAX_PAGES:
                        await delay_between_requests()

                # Delay between search terms
                await delay_between_requests()

            logger.info(f"{SOURCE_NAME} - Scraped {len(results)} unique listings total")

    except Exception as e:
        logger.error(f"{SOURCE_NAME} - Failed: {e}")
        return []

    return results


def _find_listing_container(element: Tag) -> Optional[Tag]:
    """Find the parent container of a listing link."""
    # Walk up the tree to find a suitable container
    parent = element.parent
    for _ in range(5):  # Don't go too far up
        if parent is None:
            break
        if parent.name in ("article", "div", "li") and parent.get("class"):
            return parent
        parent = parent.parent
    return element.parent if element.parent else None


def _has_next_page(soup: BeautifulSoup, current_page: int) -> bool:
    """Check if there's a next page link in pagination."""
    # Check for "Mehr Produkte laden" (Load more) button - indicates more content available
    load_more = soup.select_one("button:-soup-contains('Mehr Produkte'), a:-soup-contains('Mehr Produkte')")
    if load_more:
        return True

    # Common pagination patterns
    next_link = soup.select_one("a.next, a[rel='next'], .pagination a:-soup-contains('»'), .pagination a:-soup-contains('Weiter')")
    if next_link:
        return True

    # Check for page number links with higher page numbers
    pagination = soup.select(".pagination a[href*='page='], .pager a[href*='page=']")
    for link in pagination:
        href = link.get("href", "")
        match = re.search(r"page=(\d+)", str(href))
        if match:
            page_num = int(match.group(1))
            if page_num > current_page:
                return True

    return False


def _parse_listing(listing: Tag) -> Optional[ScraperResult]:
    """Parse a single listing element into ScraperResult."""
    # Extract title - try multiple selectors
    title = _extract_title(listing)
    if not title:
        return None

    # Extract link
    link = _extract_link(listing)
    if not link:
        return None

    # Extract price
    price = _extract_price(listing)

    # Extract image URL
    image_url = _extract_image_url(listing)

    return ScraperResult(
        title=title,
        price=price,
        image_url=image_url,
        link=link,
        source=SOURCE_NAME
    )


def _extract_title(listing: Tag) -> Optional[str]:
    """Extract title from listing element."""
    # Try common title selectors - updated for new site structure
    title_selectors = [
        ".article-list-item-title",  # New structure
        ".title",
        ".inserat-title",
        "h2",
        "h3",
        ".name",
        "a[href*='/de/-']",  # New URL pattern
        "a[href*='/inserat/']",
    ]

    for selector in title_selectors:
        elem = listing.select_one(selector)
        if elem:
            title = elem.get_text(strip=True)
            if title:
                return title

    return None


def _extract_link(listing: Tag) -> Optional[str]:
    """Extract link from listing element."""
    # If listing itself is a link (new structure uses <a> tags as containers)
    if listing.name == "a" and listing.get("href"):
        href = listing["href"]
        if isinstance(href, list):
            href = href[0]
        return make_absolute_url(BASE_URL, href)

    # Try to find the detail page link - updated for new URL pattern
    link_elem = listing.select_one("a[href*='/de/-'], a[href*='/inserat/'], a.detail-link, a")
    if link_elem and link_elem.get("href"):
        href = link_elem["href"]
        # Ensure it's a string (could be a list in some cases)
        if isinstance(href, list):
            href = href[0]
        return make_absolute_url(BASE_URL, href)

    return None


def _extract_price(listing: Tag) -> Optional[float]:
    """Extract price from listing element."""
    # Try common price selectors - updated for new site structure
    price_selectors = [
        ".article-list-item-price",  # New structure
        ".price",
        ".inserat-price",
        ".preis",
        "[class*='price']",
        "[class*='preis']",
    ]

    for selector in price_selectors:
        elem = listing.select_one(selector)
        if elem:
            price_str = elem.get_text(strip=True)
            price = parse_price(price_str)
            if price is not None:
                return price

    # Try to find price in text that contains CHF
    text = listing.get_text()
    if "CHF" in text or "Fr." in text:
        # Look for patterns like "CHF 1'234" or "1234 CHF"
        match = re.search(r"(?:CHF|Fr\.?)\s*([\d',.]+)|(\d[\d',.]*)\s*(?:CHF|Fr\.?)", text)
        if match:
            price_str = match.group(1) or match.group(2)
            return parse_price(price_str)

    return None


def _extract_image_url(listing: Tag) -> Optional[str]:
    """Extract image URL from listing element."""
    # Try common image selectors - updated for new site structure
    img_elem = listing.select_one(".article-list-item-image img, img, .image img, .thumbnail img")

    if img_elem:
        # Try different image source attributes
        for attr in ["src", "data-src", "data-lazy-src"]:
            img_url = img_elem.get(attr)
            if img_url:
                if isinstance(img_url, list):
                    img_url = img_url[0]
                # Skip placeholder images
                if "placeholder" not in img_url.lower() and "blank" not in img_url.lower():
                    return make_absolute_url(BASE_URL, img_url)

    return None
