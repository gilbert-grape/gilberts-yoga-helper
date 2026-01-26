"""
waffengebraucht.ch Scraper

Scrapes used firearms listings from waffengebraucht.ch
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

BASE_URL = "https://www.waffengebraucht.ch"
# Site uses category-based listings - kurzwaffen (handguns) and langwaffen (long guns)
CATEGORY_URLS = [
    f"{BASE_URL}/li/kurzwaffen",
    f"{BASE_URL}/li/langwaffen",
]
SOURCE_NAME = "waffengebraucht.ch"
MAX_PAGES = 10  # Reasonable limit to avoid excessive scraping


async def scrape_waffengebraucht() -> ScraperResults:
    """
    Scrape all listings from waffengebraucht.ch.

    Returns:
        List of ScraperResult dicts with title, price, image_url, link, source.
        Returns empty list on any error.
    """
    results: ScraperResults = []

    try:
        async with create_http_client() as client:
            for category_url in CATEGORY_URLS:
                page = 1
                while page <= MAX_PAGES:
                    # Construct URL for current page
                    url = category_url if page == 1 else f"{category_url}?&page={page}"

                    response = await client.get(url)
                    response.raise_for_status()

                    soup = BeautifulSoup(response.text, "lxml")

                    # Find all listing items - try multiple selector strategies
                    listings = soup.select(".inserat-item, .listing-item, article.inserat, .item")

                    # Fallback: look for links that match listing detail page pattern
                    if not listings:
                        # waffengebraucht.ch uses URLs like /location/item-name/id
                        listing_links = soup.select("a[href]")
                        listing_links = [
                            a for a in listing_links
                            if a.get("href") and re.match(r"^/[^/]+/[^/]+/\d+$", a.get("href", ""))
                        ]
                        if listing_links:
                            listings = [_find_listing_container(elem) for elem in listing_links]
                            listings = [l for l in listings if l is not None]
                            # Deduplicate by removing repeated parent containers
                            seen_ids: set[int] = set()
                            unique_listings = []
                            for listing in listings:
                                listing_id = id(listing)
                                if listing_id not in seen_ids:
                                    seen_ids.add(listing_id)
                                    unique_listings.append(listing)
                            listings = unique_listings

                    if not listings:
                        if page == 1:
                            logger.warning(f"{SOURCE_NAME} - No listings found on {category_url}, HTML structure may have changed")
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

                    logger.debug(f"{SOURCE_NAME} - {category_url} page {page}: found {page_results} listings")

                    if not _has_next_page(soup):
                        break

                    page += 1
                    if page <= MAX_PAGES:
                        await delay_between_requests()

                # Delay between categories
                if category_url != CATEGORY_URLS[-1]:
                    await delay_between_requests()

            logger.info(f"{SOURCE_NAME} - Scraped {len(results)} listings total")

    except Exception as e:
        logger.error(f"{SOURCE_NAME} - Failed: {e}")
        return []

    return results


def _find_listing_container(element: Tag) -> Optional[Tag]:
    """Find the parent container of a listing link."""
    parent = element.parent
    for _ in range(5):  # Don't go too far up
        if parent is None:
            break
        if parent.name in ("article", "div", "li") and parent.get("class"):
            return parent
        parent = parent.parent
    return element.parent if element.parent else None


def _has_next_page(soup: BeautifulSoup) -> bool:
    """Check if there's a next page link in pagination."""
    # waffengebraucht.ch pagination uses ?&page= parameter
    # Look for next page links (using :-soup-contains instead of deprecated :contains)
    next_link = soup.select_one(
        "a.next, a[rel='next'], "
        "a:-soup-contains('»'), a:-soup-contains('Weiter'), a:-soup-contains('Letzte')"
    )
    if next_link:
        href = next_link.get("href", "")
        if "page=" in str(href):
            return True

    # Check for pagination with page numbers
    pagination_links = soup.select("a[href*='page=']")
    return len(pagination_links) > 1


def _parse_listing(listing: Tag) -> Optional[ScraperResult]:
    """Parse a single listing element into ScraperResult."""
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
        source=SOURCE_NAME
    )


def _extract_title(listing: Tag) -> Optional[str]:
    """Extract title from listing element."""
    # Try common title selectors
    title_selectors = [
        ".title",
        ".inserat-title",
        "h2",
        "h3",
        ".name",
        "a[href]",  # Often the listing link contains the title
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
    # Try to find the detail page link - waffengebraucht.ch uses /location/item/id pattern
    link_elem = listing.select_one("a[href]")

    if link_elem and link_elem.get("href"):
        href = link_elem["href"]
        if isinstance(href, list):
            href = href[0]
        # Check if it looks like a listing detail URL
        if re.match(r"^/[^/]+/[^/]+/\d+$", href) or href.startswith("http"):
            return make_absolute_url(BASE_URL, href)

    # If listing itself is a link
    if listing.name == "a" and listing.get("href"):
        href = listing["href"]
        if isinstance(href, list):
            href = href[0]
        return make_absolute_url(BASE_URL, href)

    return None


def _extract_price(listing: Tag) -> Optional[float]:
    """Extract price from listing element."""
    # Try common price selectors
    price_selectors = [
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
        # waffengebraucht.ch uses formats like "550CHF" or "1.550CHF VB"
        match = re.search(r"([\d'.,]+)\s*(?:CHF|Fr\.?)|(?:CHF|Fr\.?)\s*([\d'.,]+)", text)
        if match:
            price_str = match.group(1) or match.group(2)
            return parse_price(price_str)

    return None


def _extract_image_url(listing: Tag) -> Optional[str]:
    """Extract image URL from listing element."""
    # Try common image selectors
    img_elem = listing.select_one("img, .image img, .thumbnail img")

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
