"""
Tests for ellie-firearms.com scraper.

Tests verify:
- PrestaShop product parsing
- Title, price, image, link extraction
- Pagination detection
- Error handling
"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.scrapers.ellie import (
    BASE_URL,
    SOURCE_NAME,
    scrape_ellie,
    _extract_image_url,
    _extract_link,
    _extract_price,
    _extract_title,
    _has_next_page,
    _parse_listing,
)
from bs4 import BeautifulSoup


# Sample HTML fixtures
SAMPLE_HTML_SINGLE_LISTING = """
<html>
<body>
    <article class="product-miniature">
        <a class="product-thumbnail" href="/produkt/sig-p226.html">
            <img src="/images/sig-p226.jpg">
        </a>
        <h3><a href="/produkt/sig-p226.html" title="SIG Sauer P226">SIG Sauer P226</a></h3>
        <span class="price">CHF 1'200.00</span>
    </article>
</body>
</html>
"""

SAMPLE_HTML_MULTIPLE_LISTINGS = """
<html>
<body>
    <article class="product-miniature">
        <h3><a href="/produkt/sig-p226.html">SIG P226</a></h3>
        <span class="price">CHF 1'200.00</span>
    </article>
    <article class="product-miniature">
        <h3><a href="/produkt/glock-17.html">Glock 17</a></h3>
        <span class="price">CHF 850.00</span>
    </article>
    <article class="product-miniature">
        <h3><a href="/produkt/cz-75.html">CZ 75 B</a></h3>
        <span class="price">CHF 750.00</span>
    </article>
</body>
</html>
"""

SAMPLE_HTML_NO_LISTINGS = """
<html>
<body>
    <div class="no-results">
        <p>Keine Produkte gefunden</p>
    </div>
</body>
</html>
"""

SAMPLE_HTML_WITH_PAGINATION = """
<html>
<body>
    <article class="product-miniature">
        <h3><a href="/produkt/test.html">Test Gun</a></h3>
        <span class="price">CHF 500.00</span>
    </article>
    <nav class="pagination">
        <a href="?search_query=sig&page=1">1</a>
        <a href="?search_query=sig&page=2">2</a>
        <a class="next" href="?search_query=sig&page=2">Weiter</a>
    </nav>
</body>
</html>
"""


class TestExtractTitle:
    """Tests for _extract_title helper."""

    def test_extracts_title_from_h3(self):
        """Extract title from h3 > a element."""
        html = '<article><h3><a href="/p.html">Test Gun</a></h3></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        assert _extract_title(listing) == "Test Gun"

    def test_extracts_title_from_title_attribute(self):
        """Extract title from title attribute."""
        html = '<article><h3><a href="/p.html" title="Gun Title">Short</a></h3></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        assert _extract_title(listing) == "Gun Title"

    def test_returns_none_for_missing_title(self):
        """Return None when no title found."""
        html = '<article><span>no title</span></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        assert _extract_title(listing) is None


class TestExtractPrice:
    """Tests for _extract_price helper."""

    def test_extracts_price_from_price_class(self):
        """Extract price from span.price element."""
        html = "<article><span class='price'>CHF 1'200.00</span></article>"
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        assert _extract_price(listing) == 1200.0

    def test_extracts_price_from_text(self):
        """Extract price from text containing CHF."""
        html = '<article><div>Preis: CHF 850.50</div></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        assert _extract_price(listing) == 850.5

    def test_returns_none_for_missing_price(self):
        """Return None when no price found."""
        html = '<article><span>No price</span></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        assert _extract_price(listing) is None


class TestExtractLink:
    """Tests for _extract_link helper."""

    def test_extracts_link_from_h3(self):
        """Extract link from h3 > a element."""
        html = '<article><h3><a href="/produkt/gun.html">Gun</a></h3></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        link = _extract_link(listing)
        assert link == f"{BASE_URL}/produkt/gun.html"

    def test_skips_javascript_links(self):
        """Skip javascript: links."""
        html = '<article><a href="javascript:void(0)">JS</a><a href="/p.html">Gun</a></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        link = _extract_link(listing)
        assert link == f"{BASE_URL}/p.html"

    def test_returns_none_for_missing_link(self):
        """Return None when no link found."""
        html = '<article><span>no link</span></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        assert _extract_link(listing) is None


class TestExtractImageUrl:
    """Tests for _extract_image_url helper."""

    def test_extracts_image_from_thumbnail(self):
        """Extract image from product-thumbnail."""
        html = '<article><div class="product-thumbnail"><img src="/img/gun.jpg"></div></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        img_url = _extract_image_url(listing)
        assert img_url == f"{BASE_URL}/img/gun.jpg"

    def test_extracts_image_from_data_src(self):
        """Extract image from data-src (lazy loading)."""
        html = '<article><img data-src="/img/lazy.jpg"></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        img_url = _extract_image_url(listing)
        assert img_url == f"{BASE_URL}/img/lazy.jpg"

    def test_returns_none_for_missing_image(self):
        """Return None when no image found."""
        html = '<article><span>no image</span></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        assert _extract_image_url(listing) is None

    def test_skips_placeholder_images(self):
        """Skip placeholder images."""
        html = '<article><img src="/img/placeholder.gif"></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        assert _extract_image_url(listing) is None


class TestHasNextPage:
    """Tests for _has_next_page helper."""

    def test_detects_next_class(self):
        """Detect pagination via .next class."""
        soup = BeautifulSoup(SAMPLE_HTML_WITH_PAGINATION, "lxml")
        assert _has_next_page(soup, 1) is True

    def test_detects_page_number_links(self):
        """Detect pagination via page number links in pagination class."""
        html = '<nav class="pagination"><a href="?page=2">2</a></nav>'
        soup = BeautifulSoup(html, "lxml")
        assert _has_next_page(soup, 1) is True

    def test_returns_false_for_last_page(self):
        """Return False when on last page."""
        html = '<nav><a href="?page=1">1</a><a href="?page=2">2</a></nav>'
        soup = BeautifulSoup(html, "lxml")
        assert _has_next_page(soup, 2) is False

    def test_returns_false_for_no_pagination(self):
        """Return False when no pagination."""
        soup = BeautifulSoup(SAMPLE_HTML_NO_LISTINGS, "lxml")
        assert _has_next_page(soup, 1) is False


class TestParseListing:
    """Tests for _parse_listing helper."""

    def test_parses_complete_listing(self):
        """Parse listing with all fields."""
        html = """
        <article class="product-miniature">
            <div class="product-thumbnail"><img src="/img/gun.jpg"></div>
            <h3><a href="/produkt/test.html">Test Gun</a></h3>
            <span class="price">CHF 1'000.00</span>
        </article>
        """
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        result = _parse_listing(listing)

        assert result is not None
        assert result["title"] == "Test Gun"
        assert result["price"] == 1000.0
        assert result["source"] == SOURCE_NAME

    def test_returns_none_for_missing_title(self):
        """Return None when title missing."""
        html = '<article><a href="/p.html"></a></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        assert _parse_listing(listing) is None

    def test_returns_none_for_missing_link(self):
        """Return None when link missing."""
        html = '<article><h3>Test</h3></article>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("article")
        assert _parse_listing(listing) is None


class TestScrapeEllie:
    """Tests for scrape_ellie main function."""

    @pytest.mark.asyncio
    async def test_extracts_listings(self):
        """Test listing extraction."""
        mock_response = MagicMock()
        mock_response.text = SAMPLE_HTML_MULTIPLE_LISTINGS
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.ellie.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.ellie.delay_between_requests", new_callable=AsyncMock):
                with patch("backend.services.crawler.add_crawl_log"):
                    results = await scrape_ellie(search_terms=["sig"])

        assert len(results) == 3
        assert results[0]["title"] == "SIG P226"
        assert results[0]["price"] == 1200.0

    @pytest.mark.asyncio
    async def test_returns_empty_on_http_error(self):
        """Test that HTTP errors return empty list."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.HTTPStatusError(
            "Server Error",
            request=MagicMock(),
            response=MagicMock(status_code=500)
        ))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.ellie.create_http_client", return_value=mock_client):
            with patch("backend.services.crawler.add_crawl_log"):
                results = await scrape_ellie(search_terms=["sig"])

        assert results == []

    @pytest.mark.asyncio
    async def test_returns_empty_for_empty_search_terms(self):
        """Test that empty search terms return empty list."""
        results = await scrape_ellie(search_terms=[])
        assert results == []

    @pytest.mark.asyncio
    async def test_deduplicates_across_searches(self):
        """Test deduplication across multiple search terms."""
        mock_response = MagicMock()
        mock_response.text = SAMPLE_HTML_MULTIPLE_LISTINGS
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.ellie.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.ellie.delay_between_requests", new_callable=AsyncMock):
                with patch("backend.services.crawler.add_crawl_log"):
                    results = await scrape_ellie(search_terms=["sig", "glock"])

        # Should only have 3 unique results, not 6
        assert len(results) == 3
