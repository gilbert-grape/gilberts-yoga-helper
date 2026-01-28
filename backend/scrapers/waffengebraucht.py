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

BASE_URL = "https://waffengebraucht.ch"  # Note: no www - site redirects
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
    # Import here to avoid circular dependency
    from backend.services.crawler import add_crawl_log

    results: ScraperResults = []

    try:
        async with create_http_client() as client:
            for category_url in CATEGORY_URLS:
                # Extract category name from URL for logging
                category_name = category_url.split("/")[-1]
                add_crawl_log(f"  → Kategorie: {category_name}")

                page = 1
                while page <= MAX_PAGES:
                    # Construct URL for current page
                    url = category_url if page == 1 else f"{category_url}?&page={page}"
                    add_crawl_log(f"    Seite {page}...")

                    response = await client.get(url)
                    response.raise_for_status()

                    soup = BeautifulSoup(response.text, "lxml")

                    # Find all listing items - site uses __Item class with __ItemById_ prefix
                    # Structure: .__ProductItemListener > .__Item.__ItemById_XXXXX
                    listings = soup.select(".__ProductItemListener .__Item[class*='__ItemById_']")

                    # Fallback: try other selectors
                    if not listings:
                        listings = soup.select("div[class*='__ItemById_']")

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

                    if not _has_next_page(soup, page):
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


def _has_next_page(soup: BeautifulSoup, current_page: int) -> bool:
    """Check if there's a next page link in pagination."""
    # waffengebraucht.ch pagination uses ?&page= parameter
    # Look for any pagination links with page numbers higher than current
    pagination_links = soup.select("a[href*='page=']")

    for link in pagination_links:
        href = link.get("href", "")
        # Extract page number from URL
        match = re.search(r"page=(\d+)", str(href))
        if match:
            page_num = int(match.group(1))
            if page_num > current_page:
                return True

    return False


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
    # Site uses .__ProductTitle with link inside
    title_selectors = [
        ".__ProductTitle a",
        ".__ProductTitle",
        ".title",
        "a[href]",
    ]

    for selector in title_selectors:
        elem = listing.select_one(selector)
        if elem:
            # Try title attribute first (cleaner)
            title = elem.get("title", "")
            if title:
                # Remove site suffix from title
                title = title.replace(" - Waffengebraucht.ch", "")
                return title
            # Fall back to text content
            title = elem.get_text(strip=True)
            if title:
                return title

    return None


def _extract_link(listing: Tag) -> Optional[str]:
    """Extract link from listing element."""
    # Site uses .__ProductTitle a for the main link
    link_elem = listing.select_one(".__ProductTitle a[href]")

    if not link_elem:
        # Fallback to any link
        link_elem = listing.select_one("a[href]")

    if link_elem and link_elem.get("href"):
        href = link_elem["href"]
        if isinstance(href, list):
            href = href[0]
        # URLs are already absolute on this site
        if href.startswith("http"):
            return href
        return make_absolute_url(BASE_URL, href)

    return None


def _extract_price(listing: Tag) -> Optional[float]:
    """Extract price from listing element."""
    # Site uses .__SetPriceRequest with data-price attribute
    price_elem = listing.select_one(".__SetPriceRequest[data-price]")
    if price_elem:
        data_price = price_elem.get("data-price")
        if data_price:
            try:
                return float(data_price)
            except ValueError:
                pass

    # Fallback: try to find price in .GreenInfo
    green_info = listing.select_one(".GreenInfo")
    if green_info:
        price_text = green_info.get_text(strip=True)
        price = parse_price(price_text)
        if price is not None:
            return price

    # Try other common price selectors
    price_selectors = [
        ".price",
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
        # waffengebraucht.ch uses formats like "550CHF" or "1.550CHF VB"
        match = re.search(r"([\d'.,]+)\s*(?:CHF|Fr\.?)|(?:CHF|Fr\.?)\s*([\d'.,]+)", text)
        if match:
            price_str = match.group(1) or match.group(2)
            return parse_price(price_str)

    return None


def _extract_image_url(listing: Tag) -> Optional[str]:
    """Extract image URL from listing element."""
    # Site uses .__ImageView img with lazyload (data-src)
    img_elem = listing.select_one(".__ImageView img, img.lazyload, img")

    if img_elem:
        # Try data-src first (lazyload), then src
        for attr in ["data-src", "src", "data-lazy-src"]:
            img_url = img_elem.get(attr)
            if img_url:
                if isinstance(img_url, list):
                    img_url = img_url[0]
                # Skip placeholder images (default.png is the placeholder)
                if "default.png" not in img_url.lower() and "placeholder" not in img_url.lower():
                    return make_absolute_url(BASE_URL, img_url)

    return None
