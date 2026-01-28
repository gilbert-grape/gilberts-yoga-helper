"""
waffenzimmi.ch Scraper

Scrapes used firearms listings from waffenzimmi.ch (WooCommerce site)
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

BASE_URL = "https://www.waffenzimmi.ch"
# WooCommerce site uses category-based URLs for firearms
CATEGORY_URLS = [
    f"{BASE_URL}/produkt-kategorie/waffen/kurzwaffen-waffen/",
    f"{BASE_URL}/produkt-kategorie/waffen/langwaffen-waffen/",
]
SOURCE_NAME = "waffenzimmi.ch"
MAX_PAGES = 10  # Reasonable limit to avoid excessive scraping


async def scrape_waffenzimmi() -> ScraperResults:
    """
    Scrape all listings from waffenzimmi.ch.

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
                category_name = category_url.rstrip("/").split("/")[-1].replace("-waffen", "")
                add_crawl_log(f"  → Kategorie: {category_name}")

                page = 1
                while page <= MAX_PAGES:
                    # WooCommerce pagination uses /page/N/ pattern
                    url = category_url if page == 1 else f"{category_url}page/{page}/"
                    add_crawl_log(f"    Seite {page}...")

                    response = await client.get(url)
                    response.raise_for_status()

                    soup = BeautifulSoup(response.text, "lxml")

                    # WooCommerce product listing selectors
                    listings = soup.select(
                        ".products > li, "
                        "li.product, "
                        ".product-item, "
                        "[class*='type-product']"
                    )

                    # Fallback: look for links that match product detail pages
                    if not listings:
                        product_links = soup.select("a[href*='/produkt/']")
                        if product_links:
                            listings = [_find_listing_container(elem) for elem in product_links]
                            listings = [l for l in listings if l is not None]
                            # Deduplicate
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
    """Find the parent container of a product link."""
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
    # WooCommerce pagination patterns - check for next link in various structures
    next_link = soup.select_one(
        "a.next, "
        "a.page-numbers.next, "
        "li.next a, "  # li with class next containing a link
        "a[rel='next'], "
        ".woocommerce-pagination a:-soup-contains('→'), "
        ".woocommerce-pagination a:-soup-contains('Weiter'), "
        ".pagination a:-soup-contains('Weiter')"
    )
    if next_link:
        return True

    # Check for page number links with /page/ pattern that are higher than current page
    pagination_links = soup.select("a[href*='/page/']")
    for link in pagination_links:
        href = link.get("href", "")
        # Extract page number from URL like /page/2/
        match = re.search(r"/page/(\d+)/?", str(href))
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
    # WooCommerce title selectors
    title_selectors = [
        ".woocommerce-loop-product__title",
        "h2.product-title",
        "h3.product-title",
        ".product-name",
        "h2 a",
        "h3 a",
        "h2",
        "h3",
        "a[href*='/produkt/']",
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
    # WooCommerce link selectors
    link_selectors = [
        "a.woocommerce-LoopProduct-link",
        "a[href*='/produkt/']",
        ".product-name a",
        "h2 a",
        "h3 a",
        "a",
    ]

    for selector in link_selectors:
        link_elem = listing.select_one(selector)
        if link_elem and link_elem.get("href"):
            href = link_elem["href"]
            if isinstance(href, list):
                href = href[0]
            # Verify it looks like a product URL
            if "/produkt/" in href or href.startswith("http"):
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
    # WooCommerce price selectors - check sale price first
    price_selectors = [
        ".price ins .woocommerce-Price-amount",  # Sale price (priority)
        ".price > .woocommerce-Price-amount",  # Direct child only (not inside del)
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
        # Swiss format: "CHF 1'234.00" or "1'234.00 CHF"
        match = re.search(r"(?:CHF|Fr\.?)\s*([\d'.,]+)|(\d[\d'.,]*)\s*(?:CHF|Fr\.?)", text)
        if match:
            price_str = match.group(1) or match.group(2)
            return parse_price(price_str)

    return None


def _extract_image_url(listing: Tag) -> Optional[str]:
    """Extract image URL from listing element."""
    # WooCommerce image selectors
    img_selectors = [
        "img.wp-post-image",
        "img.attachment-woocommerce_thumbnail",
        ".product-image img",
        "img",
    ]

    for selector in img_selectors:
        img_elem = listing.select_one(selector)
        if img_elem:
            # Try different image source attributes (including lazy-load)
            for attr in ["src", "data-src", "data-lazy-src", "data-original"]:
                img_url = img_elem.get(attr)
                if img_url:
                    if isinstance(img_url, list):
                        img_url = img_url[0]
                    # Skip placeholder images
                    if ("placeholder" not in img_url.lower() and
                        "blank" not in img_url.lower() and
                        "xstore-placeholder" not in img_url.lower()):
                        return make_absolute_url(BASE_URL, img_url)

    return None
