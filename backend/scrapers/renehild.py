"""
renehild-tactical.ch Scraper

Scrapes used firearms listings from the Waffenboerse category on renehild-tactical.ch
This site has no search functionality, so we scrape all products from the category pages.
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

BASE_URL = "https://renehild-tactical.ch"
LISTINGS_URL = f"{BASE_URL}/produkt-kategorie/waffenboerse/"
SOURCE_NAME = "renehild-tactical.ch"
MAX_PAGES = 10  # Site currently has ~3 pages, allow buffer for growth


async def scrape_renehild() -> ScraperResults:
    """
    Scrape all listings from renehild-tactical.ch Waffenboerse category.

    This site has no search functionality, so we scrape all products
    from the category pages using pagination.

    Returns:
        List of ScraperResult dicts with title, price, image_url, link, source.
        Returns empty list on any error.
    """
    # Import here to avoid circular dependency
    from backend.services.crawler import add_crawl_log

    results: ScraperResults = []

    try:
        from backend.services.crawler import is_cancel_requested

        async with create_http_client() as client:
            page = 1
            while page <= MAX_PAGES:
                # Check for cancellation between pages
                if is_cancel_requested():
                    logger.info(f"{SOURCE_NAME} - Cancelled by user")
                    return results
                # WooCommerce pagination uses /page/N/ path
                url = LISTINGS_URL if page == 1 else f"{LISTINGS_URL}page/{page}/"
                add_crawl_log(f"    Seite {page}...")

                response = await client.get(url)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "html.parser")

                # Find product list - WooCommerce uses ul.products or similar
                product_list = soup.select_one("ul.products, .products")
                if product_list:
                    listings = product_list.select("li.product, li")
                else:
                    # Fallback: find li elements with product links
                    listings = soup.select("li:has(a[href*='/produkt/'])")

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
    next_page_num = current_page + 1

    # WooCommerce pagination: look for page/N/ links
    next_link = soup.select_one(f"a[href*='page/{next_page_num}/']")
    if next_link:
        return True

    # Look for "next" style links (WooCommerce uses .next class)
    next_link = soup.select_one(
        "a.next, a.page-numbers.next, "
        "a:-soup-contains('→'), a:-soup-contains('Weiter'), a:-soup-contains('Nächste')"
    )
    return next_link is not None


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
        source=SOURCE_NAME,
    )


def _extract_title(listing: Tag) -> Optional[str]:
    """Extract title from listing element."""
    # WooCommerce title selectors
    title_selectors = [
        ".woocommerce-loop-product__title",
        "h2.wc-block-grid__product-title",
        "h2",
        "h3",
        "a[href*='/produkt/']",
    ]

    for selector in title_selectors:
        elem = listing.select_one(selector)
        if elem:
            title = elem.get_text(strip=True)
            if title and len(title) > 3:  # Skip very short text
                return title

    # Fallback: try to find title in link text
    links = listing.select("a[href*='/produkt/']")
    for link in links:
        text = link.get_text(strip=True)
        # Skip if it looks like a price or button
        if text and len(text) > 3 and "CHF" not in text and "Warenkorb" not in text:
            return text

    return None


def _extract_link(listing: Tag) -> Optional[str]:
    """Extract link from listing element."""
    # WooCommerce product links
    link_selectors = [
        "a.woocommerce-LoopProduct-link",
        "a[href*='/produkt/']",
        "a[href]",
    ]

    for selector in link_selectors:
        link_elem = listing.select_one(selector)
        if link_elem and link_elem.get("href"):
            href = link_elem["href"]
            if isinstance(href, list):
                href = href[0]
            # Verify it looks like a product URL
            if "/produkt/" in href:
                return make_absolute_url(BASE_URL, href)

    return None


def _extract_price(listing: Tag) -> Optional[float]:
    """Extract price from listing element."""
    # WooCommerce price selectors
    price_selectors = [
        ".price bdi",
        ".price",
        "span.woocommerce-Price-amount",
        "strong",
    ]

    for selector in price_selectors:
        elem = listing.select_one(selector)
        if elem:
            text = elem.get_text(strip=True)
            # Check if it contains CHF or looks like a price
            if "CHF" in text or re.search(r"[\d',.]+", text):
                price = parse_price(text)
                if price is not None:
                    return price

    # Fallback: search full text for price pattern
    full_text = listing.get_text()
    # Normalize unicode apostrophes
    full_text = full_text.replace("\u2019", "'").replace("\u2018", "'")

    # Swiss price format: CHF X'XXX.XX
    match = re.search(r"CHF\s*([\d',.]+)", full_text)
    if match:
        return parse_price(match.group(1))

    return None


def _extract_image_url(listing: Tag) -> Optional[str]:
    """Extract image URL from listing element."""
    img_elem = listing.select_one("img")

    if img_elem:
        # Try different image source attributes (handle lazy loading)
        for attr in ["src", "data-src", "data-lazy-src", "srcset"]:
            img_url = img_elem.get(attr)
            if img_url:
                if isinstance(img_url, list):
                    img_url = img_url[0]
                # Handle srcset (take first URL)
                if attr == "srcset" and " " in img_url:
                    img_url = img_url.split()[0]
                # Skip placeholder images
                if "placeholder" not in img_url.lower() and "blank" not in img_url.lower():
                    return make_absolute_url(BASE_URL, img_url)

    return None
