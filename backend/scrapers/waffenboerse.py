"""
waffenboerse.ch Scraper

Scrapes used firearms listings from waffenboerse.ch
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

BASE_URL = "https://www.waffenboerse.ch"
# Site uses category-based listings with infinite scroll
# Scrape each category separately to get more results
CATEGORY_URLS = [
    f"{BASE_URL}/de/occasionen/gebrauchtwaffen/faustfeuerwaffen/",  # Handguns
    f"{BASE_URL}/de/occasionen/gebrauchtwaffen/jagdwaffen/",  # Hunting rifles
    f"{BASE_URL}/de/occasionen/gebrauchtwaffen/sportwaffen/",  # Sporting weapons
    f"{BASE_URL}/de/occasionen/gebrauchtwaffen/raritaeten/",  # Rarities/Collectibles
    f"{BASE_URL}/de/occasionen/gebrauchtwaffen/blankwaffen/",  # Bladed weapons
]
SOURCE_NAME = "waffenboerse.ch"
MAX_PAGES = 10  # Reasonable limit to avoid excessive scraping
# Note: Site uses infinite scroll - we scrape first page of each category


async def scrape_waffenboerse() -> ScraperResults:
    """
    Scrape all listings from waffenboerse.ch.

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
                category_name = category_url.rstrip("/").split("/")[-1]
                add_crawl_log(f"  → Kategorie: {category_name}")

                page = 1
                while page <= MAX_PAGES:
                    # Construct URL for current page
                    url = category_url if page == 1 else f"{category_url}?page={page}"
                    add_crawl_log(f"    Seite {page}...")

                    response = await client.get(url)
                    response.raise_for_status()

                    # Parse HTML
                    soup = BeautifulSoup(response.text, "lxml")

                    # Find all listing items - updated for new site structure
                    # New structure uses .article-list-item containers
                    listings = soup.select(".article-list-item, .inserat-item, .listing-item, article.inserat")

                    # If no specific selectors work, try finding detail page links
                    if not listings:
                        # Try finding links that look like listing detail pages
                        # New URL pattern: /de/-XXXXX.html
                        listings = soup.select("a[href*='/de/-'], a[href*='/inserat/']")
                        if listings:
                            # Process parent containers instead
                            listings = [_find_listing_container(elem) for elem in listings]
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
                        # No listings found on this page
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

                    # Check if there's a next page (infinite scroll may not have traditional pagination)
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
