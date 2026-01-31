"""
petitesannonces.ch Scraper

Scrapes listings from petitesannonces.ch (Swiss French classifieds site).
Category 12 appears to be firearms/weapons related.
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

BASE_URL = "https://www.petitesannonces.ch"
# Category 12 - likely firearms/weapons
CATEGORY_URL = f"{BASE_URL}/r/12"
SEARCH_URL = f"{BASE_URL}/q"
SOURCE_NAME = "petitesannonces.ch"
MAX_PAGES = 10  # Max pages per search term


async def scrape_petitesannonces(search_terms: Optional[List[str]] = None) -> ScraperResults:
    """
    Scrape listings from petitesannonces.ch using search.

    This scraper uses the site's search functionality to find relevant listings.
    If no search_terms are provided, it will fetch them from the database.

    Args:
        search_terms: Optional list of search terms. If None, fetches from database.

    Returns:
        List of ScraperResult dicts with title, price, image_url, link, source.
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
        async with create_http_client() as client:
            for term in search_terms:
                add_crawl_log(f"  → Suche: '{term}'")

                page = 1
                while page <= MAX_PAGES:
                    # Construct search URL with query parameter
                    # petitesannonces.ch uses /q/searchterm format and ?p=N for pagination
                    encoded_term = quote_plus(term)
                    url = f"{SEARCH_URL}/{encoded_term}"
                    if page > 1:
                        url += f"?p={page}"
                    add_crawl_log(f"    Seite {page}...")

                    response = await client.get(url)
                    response.raise_for_status()

                    # Parse HTML
                    soup = BeautifulSoup(response.text, "lxml")

                    # Find all listing rows in the table
                    # The site uses a table-based layout with rows for each listing
                    listings = _find_listings(soup)

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


def _find_listings(soup: BeautifulSoup) -> List[Tag]:
    """Find all listing elements on the page."""
    listings = []

    # Try to find table rows that contain listings
    # petitesannonces.ch uses a table layout with columns for image, title, price, location, date
    # Look for rows with links to detail pages
    rows = soup.select("tr")
    for row in rows:
        # A listing row should have a link to an ad (typically /a/XXXXX pattern)
        link = row.select_one("a[href*='/a/']")
        if link:
            listings.append(row)

    # If no table rows found, try other common patterns
    if not listings:
        # Try div-based listings
        listings = soup.select(".annonce, .listing, .ad-item, [class*='annonce']")

    return listings


def _has_next_page(soup: BeautifulSoup, current_page: int) -> bool:
    """Check if there's a next page link in pagination."""
    # Look for pagination links - petitesannonces uses ?p=N format
    # Check for page number links with higher page numbers
    pagination_links = soup.select("a[href*='?p='], a[href*='&p=']")
    for link in pagination_links:
        href = link.get("href", "")
        match = re.search(r"[?&]p=(\d+)", str(href))
        if match:
            page_num = int(match.group(1))
            if page_num > current_page:
                return True

    # Also check for "next" or "suivant" (French) links
    next_link = soup.select_one("a:-soup-contains('Suivant'), a:-soup-contains('»'), a.next, a[rel='next']")
    if next_link:
        return True

    return False


def _parse_listing(listing: Tag) -> Optional[ScraperResult]:
    """Parse a single listing element into ScraperResult."""
    # Extract title
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
    # Try to find the title - usually in a link to the detail page
    # Look for link with /a/ pattern (annonce/ad)
    title_link = listing.select_one("a[href*='/a/']")
    if title_link:
        title = title_link.get_text(strip=True)
        if title:
            return title

    # Try other common selectors
    title_selectors = [
        ".title",
        ".titre",
        "h2",
        "h3",
        ".annonce-title",
        "td:nth-child(2) a",  # Second column in table (after image)
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
    # Look for link to detail page (typically /a/XXXXX pattern)
    link_elem = listing.select_one("a[href*='/a/']")
    if link_elem and link_elem.get("href"):
        href = link_elem["href"]
        if isinstance(href, list):
            href = href[0]
        return make_absolute_url(BASE_URL, href)

    # Fallback: any link in the listing
    link_elem = listing.select_one("a[href]")
    if link_elem and link_elem.get("href"):
        href = link_elem["href"]
        if isinstance(href, list):
            href = href[0]
        # Skip category/navigation links
        if "/r/" not in href and "/q/" not in href:
            return make_absolute_url(BASE_URL, href)

    return None


def _extract_price(listing: Tag) -> Optional[float]:
    """Extract price from listing element."""
    # petitesannonces.ch shows prices like "270.-" or "1'234.-"
    # Look for price in dedicated column or element
    price_selectors = [
        ".price",
        ".prix",
        "[class*='price']",
        "[class*='prix']",
        "td:nth-child(3)",  # Third column (price column in table)
    ]

    for selector in price_selectors:
        elem = listing.select_one(selector)
        if elem:
            price_str = elem.get_text(strip=True)
            price = parse_price(price_str)
            if price is not None:
                return price

    # Try to find price pattern in the listing text
    # Swiss format: "270.-" or "1'234.-" or "CHF 500"
    text = listing.get_text()
    # Pattern for Swiss price format with .- suffix
    match = re.search(r"(\d[\d']*)\s*\.-", text)
    if match:
        price_str = match.group(1)
        return parse_price(price_str)

    # Pattern for CHF prefix
    match = re.search(r"(?:CHF|Fr\.?)\s*([\d',.]+)", text)
    if match:
        return parse_price(match.group(1))

    return None


def _extract_image_url(listing: Tag) -> Optional[str]:
    """Extract image URL from listing element."""
    # Look for thumbnail image
    img_elem = listing.select_one("img")

    if img_elem:
        # Try different image source attributes
        for attr in ["src", "data-src", "data-lazy-src"]:
            img_url = img_elem.get(attr)
            if img_url:
                if isinstance(img_url, list):
                    img_url = img_url[0]
                # Skip placeholder images
                if "placeholder" not in img_url.lower() and "blank" not in img_url.lower():
                    # petitesannonces.ch uses paths like /i/s/523/... for thumbnails
                    return make_absolute_url(BASE_URL, img_url)

    return None
