"""
armashop.ch Scraper

Scrapes firearms listings from armashop.ch using their WooCommerce REST API.
The API is publicly accessible and returns JSON data with product information.

API Endpoint: https://armashop.ch/wp-json/wc/store/products?search=<term>
"""
import html
from typing import List, Optional

from backend.scrapers.base import (
    ScraperResult,
    ScraperResults,
    create_http_client,
    delay_between_requests,
)
from backend.utils.logging import get_logger

logger = get_logger(__name__)

BASE_URL = "https://armashop.ch"
API_URL = "https://armashop.ch/wp-json/wc/store/products"
SOURCE_NAME = "armashop.ch"
MAX_PRODUCTS_PER_TERM = 50


async def scrape_armashop(search_terms: Optional[List[str]] = None) -> ScraperResults:
    """
    Scrape listings from armashop.ch using WooCommerce Store API.

    The API returns product data including name, price, images, and permalink.
    Prices are returned in centimes (divide by 100 for CHF).

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
    seen_ids = set()  # Deduplicate products across searches

    try:
        async with create_http_client() as client:
            for term in search_terms:
                add_crawl_log(f"  → Suche: '{term}'")

                # Build API URL with search parameter
                encoded_term = quote_plus(term)
                api_url = f"{API_URL}?search={encoded_term}&per_page={MAX_PRODUCTS_PER_TERM}"

                try:
                    response = await client.get(api_url)
                    response.raise_for_status()

                    products = response.json()

                    if not products:
                        add_crawl_log(f"    Keine Ergebnisse für '{term}'")
                        await delay_between_requests()
                        continue

                    # Filter to only French language products (avoid duplicates from DE/EN)
                    # Products have 3 versions (FR, DE, EN) with same SKU
                    # We keep only one by checking if we've seen this product ID
                    new_products = 0
                    for product in products:
                        product_id = product.get("id")
                        sku = product.get("sku", "")

                        # Use SKU for deduplication (same product in different languages)
                        if sku in seen_ids:
                            continue
                        if sku:
                            seen_ids.add(sku)
                        else:
                            # Fallback to ID if no SKU
                            if product_id in seen_ids:
                                continue
                            seen_ids.add(product_id)

                        # Extract product data
                        name = product.get("name", "")
                        # Decode HTML entities in name (e.g., &#215; -> ×)
                        name = html.unescape(name)

                        permalink = product.get("permalink", "")

                        # Price is in centimes, convert to CHF
                        prices = product.get("prices", {})
                        price_centimes = prices.get("price")
                        price = None
                        if price_centimes:
                            try:
                                price = int(price_centimes) / 100
                            except (ValueError, TypeError):
                                price = None

                        # Get image URL - prefer full size, fallback to thumbnail
                        images = product.get("images", [])
                        image_url = None
                        if images:
                            image_url = images[0].get("src") or images[0].get("thumbnail")

                        # Skip products without essential data
                        if not name or not permalink:
                            continue

                        result = ScraperResult(
                            title=name,
                            price=price,
                            image_url=image_url,
                            link=permalink,
                            source=SOURCE_NAME,
                        )
                        results.append(result)
                        new_products += 1

                    add_crawl_log(f"    {new_products} Produkte gefunden")

                except Exception as e:
                    logger.warning(f"{SOURCE_NAME} - Search failed for '{term}': {e}")
                    add_crawl_log(f"    Fehler bei '{term}': {e}")
                    continue

                # Delay between search terms
                await delay_between_requests()

            logger.info(f"{SOURCE_NAME} - Scraped {len(results)} unique listings total")

    except Exception as e:
        logger.error(f"{SOURCE_NAME} - Failed: {e}")
        return []

    return results
