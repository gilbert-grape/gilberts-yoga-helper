"""
ellie-firearms.com Scraper

Scrapes firearms listings from ellie-firearms.com using their search functionality.
Site is based on PrestaShop.
"""
import re
from typing import List, Optional
from urllib.parse import quote_plus

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

BASE_URL = "https://ellie-firearms.com"
SEARCH_URL = f"{BASE_URL}/suche"
SOURCE_NAME = "ellie-firearms.com"
MAX_PAGES = 5  # Max pages per search term


async def scrape_ellie(search_terms: Optional[List[str]] = None) -> ScraperResults:
    """
    Scrape listings from ellie-firearms.com using search.

    This scraper uses the site's search functionality to find relevant listings.
    If no search_terms are provided, it will fetch them from the database.

    Args:
        search_terms: Optional list of search terms. If None, fetches from database.

    Returns:
        List of ScraperResult dicts with title, price, image_url, link, source.
        Returns empty list on any error.
    """
    from backend.services.crawler import add_crawl_log

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
                    url = f"{SEARCH_URL}?search_query={encoded_term}"
                    if page > 1:
                        url += f"&page={page}"
                    add_crawl_log(f"    Seite {page}...")

                    response = await client.get(url)
                    response.raise_for_status()

                    # Parse HTML
                    soup = BeautifulSoup(response.text, "lxml")

                    # Find all product items - PrestaShop uses article.product-miniature
                    listings = soup.select("article.product-miniature, div.product-miniature")

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


def _has_next_page(soup: BeautifulSoup, current_page: int) -> bool:
    """Check if there's a next page link in pagination."""
    # PrestaShop pagination - look for next link or page numbers
    next_link = soup.select_one("a.next, a[rel='next'], .pagination a:-soup-contains('Weiter'), .pagination a:-soup-contains('»')")
    if next_link:
        return True

    # Check for page number links with higher page numbers
    pagination = soup.select(".pagination a[href*='page='], ul.page-list a[href*='page=']")
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
    # PrestaShop product title selectors
    title_selectors = [
        "h3 a",
        ".product-title a",
        "h2.product-title a",
        "h3.product-title a",
        ".product-name a",
        "h2 a",
        ".title a",
        "a.product-name",
    ]

    for selector in title_selectors:
        elem = listing.select_one(selector)
        if elem:
            # Try title attribute first, then text content
            title = elem.get("title") or elem.get_text(strip=True)
            if title:
                return title

    return None


def _extract_link(listing: Tag) -> Optional[str]:
    """Extract link from listing element."""
    # Try PrestaShop product link selectors
    link_selectors = [
        "h3 a",
        ".product-title a",
        "h2.product-title a",
        "h3.product-title a",
        ".product-name a",
        "a.product-name",
        ".thumbnail a",
        "a.product-thumbnail",
        "a[href*='.html']",
        "a",
    ]

    for selector in link_selectors:
        link_elem = listing.select_one(selector)
        if link_elem and link_elem.get("href"):
            href = link_elem["href"]
            if isinstance(href, list):
                href = href[0]
            # Only accept product links
            if href and not href.startswith("#") and not href.startswith("javascript:"):
                return make_absolute_url(BASE_URL, href)

    return None


def _extract_price(listing: Tag) -> Optional[float]:
    """Extract price from listing element."""
    # PrestaShop price selectors
    price_selectors = [
        "span.price",
        ".product-price-and-shipping .price",
        ".price",
        ".product-price",
        "[itemprop='price']",
        ".current-price",
        "[class*='price']",
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
        match = re.search(r"(?:CHF|Fr\.?)\s*([\d\s',.]+)|(\d[\d\s',.]*)\s*(?:CHF|Fr\.?)", text)
        if match:
            price_str = match.group(1) or match.group(2)
            return parse_price(price_str)

    return None


def _extract_image_url(listing: Tag) -> Optional[str]:
    """Extract image URL from listing element."""
    # PrestaShop image selectors
    img_selectors = [
        ".product-thumbnail img",
        ".thumbnail img",
        ".product-cover img",
        ".product-image img",
        "img.product-image",
        "img",
    ]

    for selector in img_selectors:
        img_elem = listing.select_one(selector)
        if img_elem:
            # Try different image source attributes (lazy loading support)
            for attr in ["src", "data-src", "data-lazy-src", "data-full-size-image-url"]:
                img_url = img_elem.get(attr)
                if img_url:
                    if isinstance(img_url, list):
                        img_url = img_url[0]
                    # Skip placeholder images
                    if "placeholder" not in img_url.lower() and "blank" not in img_url.lower():
                        return make_absolute_url(BASE_URL, img_url)

    return None
