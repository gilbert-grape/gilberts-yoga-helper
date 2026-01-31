"""
Tests for vnsm.ch scraper.

Tests verify:
- Successful extraction of listing data (title, price, image_url, link, source)
- Price extraction including Swiss format with CHF
- PrestaShop-style pagination
- Search functionality
- Error handling returns empty list
"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.scrapers.vnsm import (
    BASE_URL,
    SOURCE_NAME,
    scrape_vnsm,
    _extract_image_url,
    _extract_link,
    _extract_price,
    _extract_title,
    _has_next_page,
    _parse_listing,
)
from bs4 import BeautifulSoup


# Sample HTML fixtures mimicking vnsm.ch PrestaShop structure
SAMPLE_HTML_SINGLE_LISTING = """
<html>
<body>
    <div class="products">
        <article class="product-miniature">
            <a href="/waffen/sig-p226" class="product-thumbnail">
                <img src="/images/sig-p226.jpg">
            </a>
            <h2 class="product-title"><a href="/waffen/sig-p226">SIG Sauer P226</a></h2>
            <div class="product-price-and-shipping">
                <span class="price">CHF 1'200.00</span>
            </div>
        </article>
    </div>
</body>
</html>
"""

SAMPLE_HTML_MULTIPLE_LISTINGS = """
<html>
<body>
    <div class="products">
        <article class="product-miniature">
            <a href="/waffen/sig-p226" class="product-thumbnail">
                <img src="/images/sig-p226.jpg">
            </a>
            <h2 class="product-title"><a href="/waffen/sig-p226">SIG P226</a></h2>
            <span class="price">CHF 1'200.00</span>
        </article>
        <article class="product-miniature">
            <a href="/waffen/glock-17" class="product-thumbnail">
                <img src="/images/glock-17.jpg">
            </a>
            <h2 class="product-title"><a href="/waffen/glock-17">Glock 17 Gen5</a></h2>
            <span class="price">CHF 850.00</span>
        </article>
        <article class="product-miniature">
            <a href="/waffen/cz-75" class="product-thumbnail">
                <img src="/images/cz-75.jpg">
            </a>
            <h2 class="product-title"><a href="/waffen/cz-75">CZ 75 B</a></h2>
            <span class="price">CHF 750.00</span>
        </article>
    </div>
</body>
</html>
"""

SAMPLE_HTML_NO_LISTINGS = """
<html>
<body>
    <div class="no-products">
        <p>Aucun produit ne correspond à votre recherche</p>
    </div>
</body>
</html>
"""

SAMPLE_HTML_WITH_PAGINATION = """
<html>
<body>
    <div class="products">
        <article class="product-miniature">
            <h2 class="product-title"><a href="/waffen/test-gun">Test Gun</a></h2>
            <span class="price">CHF 500.00</span>
        </article>
    </div>
    <nav class="pagination">
        <ul class="page-list">
            <li><a href="?s=glock&page=1">1</a></li>
            <li><a href="?s=glock&page=2">2</a></li>
            <li><a href="?s=glock&page=3">3</a></li>
            <li><a class="next" href="?s=glock&page=2">Suivant</a></li>
        </ul>
    </nav>
</body>
</html>
"""


class TestScrapeVnsm:
    """Tests for scrape_vnsm main function."""

    @pytest.mark.asyncio
    async def test_extracts_single_listing(self):
        """Test that scraper extracts a single listing correctly."""
        mock_response = MagicMock()
        mock_response.text = SAMPLE_HTML_SINGLE_LISTING
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.vnsm.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.vnsm.delay_between_requests", new_callable=AsyncMock):
                with patch("backend.services.crawler.add_crawl_log"):
                    results = await scrape_vnsm(search_terms=["sig"])

        assert len(results) == 1
        assert results[0]["title"] == "SIG Sauer P226"
        assert results[0]["price"] == 1200.0
        assert results[0]["source"] == SOURCE_NAME

    @pytest.mark.asyncio
    async def test_extracts_multiple_listings(self):
        """Test that scraper extracts multiple listings."""
        mock_response = MagicMock()
        mock_response.text = SAMPLE_HTML_MULTIPLE_LISTINGS
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.vnsm.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.vnsm.delay_between_requests", new_callable=AsyncMock):
                with patch("backend.services.crawler.add_crawl_log"):
                    results = await scrape_vnsm(search_terms=["glock"])

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_deduplicates_across_searches(self):
        """Test that duplicate results are removed across multiple searches."""
        mock_response = MagicMock()
        mock_response.text = SAMPLE_HTML_SINGLE_LISTING
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.vnsm.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.vnsm.delay_between_requests", new_callable=AsyncMock):
                with patch("backend.services.crawler.add_crawl_log"):
                    # Search with two terms that return the same product
                    results = await scrape_vnsm(search_terms=["sig", "p226"])

        # Should only have 1 result even though we searched with 2 terms
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_http_error(self):
        """Test that HTTP errors return empty list."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.HTTPStatusError(
            "Server Error",
            request=MagicMock(),
            response=MagicMock(status_code=500)
        ))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.vnsm.create_http_client", return_value=mock_client):
            with patch("backend.services.crawler.add_crawl_log"):
                results = await scrape_vnsm(search_terms=["sig"])

        assert results == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_connection_error(self):
        """Test that connection errors return empty list."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.vnsm.create_http_client", return_value=mock_client):
            with patch("backend.services.crawler.add_crawl_log"):
                results = await scrape_vnsm(search_terms=["glock"])

        assert results == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_empty_search_terms(self):
        """Test that empty search terms return empty list."""
        results = await scrape_vnsm(search_terms=[])
        assert results == []


class TestExtractTitle:
    """Tests for _extract_title helper function."""

    def test_extracts_title_from_product_title_class(self):
        """Extract title from PrestaShop product-title class."""
        html = '<article><h2 class="product-title"><a href="/gun">Test Gun</a></h2></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        assert _extract_title(listing) == "Test Gun"

    def test_extracts_title_from_h3(self):
        """Extract title from h3 element."""
        html = '<article><h3 class="product-title"><a href="/gun">Test Gun</a></h3></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        assert _extract_title(listing) == "Test Gun"

    def test_extracts_title_from_product_name(self):
        """Extract title from product-name class."""
        html = '<article><a class="product-name" href="/gun">Test Gun Name</a></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        assert _extract_title(listing) == "Test Gun Name"

    def test_returns_none_for_missing_title(self):
        """Return None when no title element found."""
        html = '<article><span>no title</span></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        assert _extract_title(listing) is None


class TestExtractPrice:
    """Tests for _extract_price helper function."""

    def test_extracts_price_from_price_class(self):
        """Extract price from price class."""
        html = "<article><span class='price'>CHF 1'200.00</span></article>"
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        assert _extract_price(listing) == 1200.0

    def test_extracts_price_from_product_price(self):
        """Extract price from product-price class."""
        html = '<article><span class="product-price">CHF 850.50</span></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        assert _extract_price(listing) == 850.5

    def test_extracts_price_from_itemprop(self):
        """Extract price from itemprop attribute."""
        html = '<article><span itemprop="price">750.00</span></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        assert _extract_price(listing) == 750.0

    def test_extracts_price_from_full_text(self):
        """Extract price from full listing text with CHF."""
        html = '<article><div>Preis: CHF 500.00</div></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        assert _extract_price(listing) == 500.0

    def test_extracts_price_with_fr_prefix(self):
        """Extract price with Fr. prefix."""
        html = '<article><div>Fr. 1\'500.00</div></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        assert _extract_price(listing) == 1500.0

    def test_returns_none_for_missing_price(self):
        """Return None when no price found."""
        html = '<article><span>No price here</span></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        assert _extract_price(listing) is None


class TestExtractLink:
    """Tests for _extract_link helper function."""

    def test_extracts_link_from_product_title(self):
        """Extract link from product-title anchor."""
        html = '<article><h2 class="product-title"><a href="/waffen/sig-p226">SIG</a></h2></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        link = _extract_link(listing)
        assert link == f"{BASE_URL}/waffen/sig-p226"

    def test_extracts_link_from_thumbnail(self):
        """Extract link from product thumbnail."""
        html = '<article><a class="product-thumbnail" href="/waffen/glock">Img</a></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        link = _extract_link(listing)
        assert link == f"{BASE_URL}/waffen/glock"

    def test_returns_none_for_missing_link(self):
        """Return None when no valid link found."""
        html = '<article><span>No link</span></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        assert _extract_link(listing) is None

    def test_extracts_first_valid_link(self):
        """Extract first valid link from listing."""
        html = '<article><h2 class="product-title"><a href="/waffen/gun">Gun</a></h2></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        link = _extract_link(listing)
        assert link == f"{BASE_URL}/waffen/gun"


class TestExtractImageUrl:
    """Tests for _extract_image_url helper function."""

    def test_extracts_image_from_product_thumbnail(self):
        """Extract image URL from product thumbnail."""
        html = '<article><div class="product-thumbnail"><img src="/images/gun.jpg"></div></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        image_url = _extract_image_url(listing)
        assert image_url == f"{BASE_URL}/images/gun.jpg"

    def test_extracts_image_from_data_src(self):
        """Extract image URL from data-src attribute (lazy loading)."""
        html = '<article><img data-src="/images/lazy.jpg"></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        image_url = _extract_image_url(listing)
        assert image_url == f"{BASE_URL}/images/lazy.jpg"

    def test_returns_none_for_missing_image(self):
        """Return None when no image found."""
        html = '<article><span>No image</span></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        assert _extract_image_url(listing) is None

    def test_skips_placeholder_images(self):
        """Skip images that are placeholders."""
        html = '<article><img src="/images/placeholder.gif"></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        assert _extract_image_url(listing) is None


class TestHasNextPage:
    """Tests for _has_next_page helper function."""

    def test_detects_next_page_link(self):
        """Detect pagination with page number links."""
        soup = BeautifulSoup(SAMPLE_HTML_WITH_PAGINATION, "lxml")
        assert _has_next_page(soup, current_page=1) is True

    def test_returns_false_for_no_pagination(self):
        """Return False when no pagination found."""
        soup = BeautifulSoup(SAMPLE_HTML_NO_LISTINGS, "lxml")
        assert _has_next_page(soup, current_page=1) is False

    def test_returns_false_when_on_last_page(self):
        """Return False when on last page."""
        html = """
        <html><body>
            <ul class="page-list">
                <a href="?page=1">1</a>
                <a href="?page=2">2</a>
            </ul>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        assert _has_next_page(soup, current_page=2) is False

    def test_detects_suivant_link(self):
        """Detect pagination via 'Suivant' (French for Next) link."""
        html = """
        <html><body>
            <nav class="pagination">
                <a href="?page=2">Suivant</a>
            </nav>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        assert _has_next_page(soup, current_page=1) is True

    def test_detects_next_class(self):
        """Detect pagination via .next class."""
        html = """
        <html><body>
            <a class="next" href="?page=2">→</a>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        assert _has_next_page(soup, current_page=1) is True


class TestParseListing:
    """Tests for _parse_listing helper function."""

    def test_parses_complete_listing(self):
        """Parse a listing with all fields."""
        html = """
        <article class="product-miniature">
            <a href="/waffen/test-gun" class="product-thumbnail">
                <img src="/images/gun.jpg">
            </a>
            <h2 class="product-title"><a href="/waffen/test-gun">Test Gun</a></h2>
            <span class="price">CHF 1'000.00</span>
        </article>
        """
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        result = _parse_listing(listing)

        assert result is not None
        assert result["title"] == "Test Gun"
        assert result["price"] == 1000.0
        assert result["link"] == f"{BASE_URL}/waffen/test-gun"
        assert result["image_url"] == f"{BASE_URL}/images/gun.jpg"
        assert result["source"] == SOURCE_NAME

    def test_returns_none_for_missing_title(self):
        """Return None when title is missing."""
        html = '<article><a href="/product/item"></a></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        result = _parse_listing(listing)
        assert result is None

    def test_returns_none_for_missing_link(self):
        """Return None when link is missing."""
        html = '<article><h2 class="product-title">Test</h2></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        result = _parse_listing(listing)
        assert result is None

    def test_handles_partial_data(self):
        """Handle listing with only required fields (title, link)."""
        html = """
        <article class="product-miniature">
            <h2 class="product-title"><a href="/waffen/test-gun">Test Gun</a></h2>
        </article>
        """
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        result = _parse_listing(listing)

        assert result is not None
        assert result["title"] == "Test Gun"
        assert result["link"] == f"{BASE_URL}/waffen/test-gun"
        assert result["price"] is None
        assert result["image_url"] is None
