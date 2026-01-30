"""
aebiwaffen.ch Scraper

Scrapes used firearms listings from aebiwaffen.ch
"""
import re
from typing import Optional

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

BASE_URL = "https://www.aebiwaffen.ch"
LISTINGS_URL = f"{BASE_URL}/de/waffen-neu-waffen-gebraucht-waffen"
SOURCE_NAME = "aebiwaffen.ch"
MAX_PAGES = 70  # Site has ~66 pages, allow some buffer


async def scrape_aebiwaffen() -> ScraperResults:
    """
    Scrape all listings from aebiwaffen.ch.

    Returns:
        List of ScraperResult dicts with title, price, image_url, link, source.
        Returns empty list on any error.
    """
    # Import here to avoid circular dependency
    from backend.services.crawler import add_crawl_log

    results: ScraperResults = []

    try:
        async with create_http_client() as client:
            page = 1
            while page <= MAX_PAGES:
                # Pagination uses ?seite=N parameter
                url = LISTINGS_URL if page == 1 else f"{LISTINGS_URL}?seite={page}"
                add_crawl_log(f"    Seite {page}...")

                response = await client.get(url)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "lxml")

                # Find product list - products are in <li> elements
                # Look for the product list container first
                product_list = soup.select_one("ul.product-list, ul.products, .product-list")
                if product_list:
                    listings = product_list.select("li")
                else:
                    # Products have h3 (title) and img (image) - this is the most reliable selector
                    listings = soup.select("li:has(h3):has(img)")
                    if not listings:
                        # Fallback: find li elements with product links (numeric ID pattern)
                        listings = soup.select("li:has(a[href*='/de/'][href*='waffen'])")

                if not listings:
                    if page == 1:
                        logger.warning(
                            f"{SOURCE_NAME} - No listings found, HTML structure may have changed"
                        )
                    break

                page_results = 0
                for listing in listings:
                    try:
                        result = _parse_listing(listing)
                        if result:
                            results.append(result)
                            page_results += 1
                    except Exception as e:
                        logger.warning(f"{SOURCE_NAME} - Failed to parse listing: {e}")
                        continue

                logger.debug(f"{SOURCE_NAME} - Page {page}: found {page_results} listings")

                # No new results means we've reached the end
                if page_results == 0:
                    break

                # Check if there's a next page
                if not _has_next_page(soup, page):
                    break

                page += 1
                if page <= MAX_PAGES:
                    await delay_between_requests()

            logger.info(f"{SOURCE_NAME} - Scraped {len(results)} listings from {page} page(s)")

    except Exception as e:
        logger.error(f"{SOURCE_NAME} - Failed: {e}")
        return []

    return results


def _has_next_page(soup: BeautifulSoup, current_page: int) -> bool:
    """Check if there's a next page link in pagination."""
    # Look for pagination links with seite parameter
    next_page_num = current_page + 1
    next_link = soup.select_one(f"a[href*='seite={next_page_num}']")
    if next_link:
        return True

    # Look for "next" style links
    next_link = soup.select_one(
        "a.next, a[rel='next'], "
        "a:-soup-contains('»'), a:-soup-contains('Weiter'), a:-soup-contains('Nächste')"
    )
    return next_link is not None


def _is_available(listing: Tag) -> bool:
    """
    Check if item is available (not ordered/bestellt).

    Items with a blue circle showing "0" are ordered but not available.
    Returns True if available, False if ordered (availability = 0).
    """
    # Look for availability indicator - typically a badge/circle with a number
    # Common patterns: span with number, badge element, availability class
    availability_selectors = [
        ".availability",
        ".stock",
        ".badge",
        "span.circle",
        "[class*='available']",
        "[class*='stock']",
    ]

    for selector in availability_selectors:
        elem = listing.select_one(selector)
        if elem:
            text = elem.get_text(strip=True)
            # If it shows "0", item is not available
            if text == "0":
                return False

    # Also check for any element that just contains "0" as availability indicator
    # Look for small text elements that might be the blue circle
    for elem in listing.select("span, div"):
        text = elem.get_text(strip=True)
        # Check if this is just a "0" (availability indicator)
        if text == "0":
            # Verify it's likely an availability indicator (small element, not price)
            classes = elem.get("class", [])
            class_str = " ".join(classes) if classes else ""
            # Skip if it's clearly part of a price
            if "price" not in class_str.lower():
                return False

    return True


def _parse_listing(listing: Tag) -> Optional[ScraperResult]:
    """Parse a single listing element into ScraperResult."""
    # Skip items with availability 0 (bestellt/ordered - not actually available)
    if not _is_available(listing):
        return None

    title = _extract_title(listing)
    if not title:
        return None

    link = _extract_link(listing)
    if not link:
        return None

    price = _extract_price(listing)
    image_url = _extract_image_url(listing)

    return ScraperResult(
        title=title,
        price=price,
        image_url=image_url,
        link=link,
        source=SOURCE_NAME,
    )


def _extract_title(listing: Tag) -> Optional[str]:
    """Extract title from listing element."""
    # Title is in h3 > a structure
    title_selectors = [
        "h3 a",
        "h3",
        "a[href*='/de/']",
    ]

    for selector in title_selectors:
        elem = listing.select_one(selector)
        if elem:
            title = elem.get_text(strip=True)
            if title and len(title) > 3:  # Skip very short text
                return title

    return None


def _extract_link(listing: Tag) -> Optional[str]:
    """Extract link from listing element."""
    # Product links have format /de/{id}/{slug}
    link_selectors = [
        "h3 a[href]",
        "a[href*='/de/']",
        "a[href]",
    ]

    for selector in link_selectors:
        link_elem = listing.select_one(selector)
        if link_elem and link_elem.get("href"):
            href = link_elem["href"]
            if isinstance(href, list):
                href = href[0]
            # Verify it looks like a product URL (has numeric ID)
            if re.search(r"/de/\d+/", href):
                return make_absolute_url(BASE_URL, href)

    return None


def _extract_price(listing: Tag) -> Optional[float]:
    """Extract price from listing element."""
    # Price format: "6'950.00 / Stk." in a div
    # Look for text containing price pattern
    text = listing.get_text()

    # Normalize unicode apostrophes/quotes to standard apostrophe
    # U+2019 (') RIGHT SINGLE QUOTATION MARK is commonly used
    text = text.replace("\u2019", "'").replace("\u2018", "'")

    # Swiss price format: digits with apostrophe thousands separator, then .00 / Stk.
    # Pattern: 1'234.56 / Stk. or 1234.00 / Stk.
    match = re.search(r"([\d']+\.?\d*)\s*/\s*Stk\.", text)
    if match:
        price_str = match.group(1)
        return parse_price(price_str)

    # Fallback: look for CHF pattern
    if "CHF" in text or "Fr." in text:
        match = re.search(r"(?:CHF|Fr\.?)\s*([\d',.]+)|([\d',.]+)\s*(?:CHF|Fr\.?)", text)
        if match:
            price_str = match.group(1) or match.group(2)
            return parse_price(price_str)

    return None


def _extract_image_url(listing: Tag) -> Optional[str]:
    """Extract image URL from listing element."""
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
                    return make_absolute_url(BASE_URL, img_url)

    return None
