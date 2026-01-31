"""
petitesannonces.ch Scraper

Scrapes listings from petitesannonces.ch (Swiss French classifieds site).
Category 12 (tid=12) is the weapons/firearms category.
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
# Search URL with tid=12 to filter to weapons category
SEARCH_URL = f"{BASE_URL}/recherche/"
SOURCE_NAME = "petitesannonces.ch"
MAX_PAGES = 10  # Max pages per search term
CATEGORY_ID = "12"  # Armes (weapons) category


async def scrape_petitesannonces(search_terms: Optional[List[str]] = None) -> ScraperResults:
    """
    Scrape listings from petitesannonces.ch using search.

    This scraper uses the site's search functionality to find relevant listings
    in the weapons category (tid=12).

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
                    # Construct search URL: /recherche/?q=term&tid=12&p=N
                    encoded_term = quote_plus(term)
                    url = f"{SEARCH_URL}?q={encoded_term}&tid={CATEGORY_ID}"
                    if page > 1:
                        url += f"&p={page}"
                    add_crawl_log(f"    Seite {page}...")

                    response = await client.get(url)
                    response.raise_for_status()

                    # Parse HTML
                    soup = BeautifulSoup(response.text, "lxml")

                    # Find all listings (both normal and premium)
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
    """Find all listing elements on the page.

    The site has two types of listings:
    - Normal listings: div.ele (with child divs for image, title, price, location, date)
    - Premium listings: div.box (featured ads at the top)
    """
    listings = []

    # Find normal listings (div.ele contains the listing row)
    normal_listings = soup.select("div.ele")
    listings.extend(normal_listings)

    # Find premium listings (div.box with ad links)
    premium_boxes = soup.select("div.box")
    for box in premium_boxes:
        # Only include if it has an ad link (not just any box)
        if box.select_one("a[href^='/a/']"):
            listings.append(box)

    return listings


def _has_next_page(soup: BeautifulSoup, current_page: int) -> bool:
    """Check if there's a next page link in pagination."""
    # Look for pagination links with ?p=N or &p=N
    pagination_links = soup.select("a[href*='&p='], a[href*='?p=']")
    for link in pagination_links:
        href = link.get("href", "")
        match = re.search(r"[?&]p=(\d+)", str(href))
        if match:
            page_num = int(match.group(1))
            if page_num > current_page:
                return True

    # Check for "Suivant" (Next) or >> links
    next_link = soup.select_one("a:-soup-contains('Suivant'), a:-soup-contains('»'), a.next")
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
    """Extract title from listing element.

    Normal listings: title is in div.elm > a
    Premium listings: title is in div.prmt > a
    """
    # Try normal listing structure first (div.elm contains the title link)
    title_elem = listing.select_one("div.elm a")
    if title_elem:
        title = title_elem.get_text(strip=True)
        if title:
            return title

    # Try premium listing structure (div.prmt contains the title link)
    title_elem = listing.select_one("div.prmt a")
    if title_elem:
        title = title_elem.get_text(strip=True)
        if title:
            return title

    # Fallback: any link with /a/ path that has text
    for link in listing.select("a[href^='/a/']"):
        text = link.get_text(strip=True)
        if text and len(text) > 5:
            return text

    return None


def _extract_link(listing: Tag) -> Optional[str]:
    """Extract link from listing element."""
    # Look for link to detail page (/a/XXXXX pattern)
    link_elem = listing.select_one("a[href^='/a/']")
    if link_elem and link_elem.get("href"):
        href = link_elem["href"]
        if isinstance(href, list):
            href = href[0]
        return make_absolute_url(BASE_URL, href)

    return None


def _extract_price(listing: Tag) -> Optional[float]:
    """Extract price from listing element.

    Normal listings: price is in div.ela.elsp or div.elsp
    Premium listings: price might be in the description text
    Prices are in Swiss format: "1'234.-" or "500.-"
    """
    # Try normal listing price element (div with both ela and elsp classes)
    price_elem = listing.select_one("div.elsp, div.ela.elsp")
    if price_elem:
        price_str = price_elem.get_text(strip=True)
        price = parse_price(price_str)
        if price is not None:
            return price

    # Try to find price pattern in text
    # Swiss format: "1'234.-" or "500.-"
    text = listing.get_text()

    # Pattern for Swiss price with .- suffix
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
    """Extract image URL from listing element.

    Normal listings: image in div.elf > a > img
    Premium listings: image in a > img directly
    """
    # Try normal listing image (in div.elf)
    img_elem = listing.select_one("div.elf img")
    if not img_elem:
        # Try premium listing or any image
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
