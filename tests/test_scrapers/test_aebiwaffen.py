"""
Tests for aebiwaffen.ch scraper.

Tests verify:
- Successful extraction of listing data (title, price, image_url, link, source)
- Price extraction including Swiss format
- URL handling
- Error handling returns empty list
- Pagination detection
"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.scrapers.aebiwaffen import (
    BASE_URL,
    SOURCE_NAME,
    scrape_aebiwaffen,
    _extract_image_url,
    _extract_link,
    _extract_price,
    _extract_title,
    _has_next_page,
    _parse_listing,
)
from bs4 import BeautifulSoup


# Sample HTML fixtures mimicking aebiwaffen.ch structure
SAMPLE_HTML_SINGLE_LISTING = """
<html>
<body>
    <ul class="product-list">
        <li>
            <h3><a href="/de/12345/sig-sauer-p226">SIG Sauer P226</a></h3>
            <img src="/images/gun1.jpg">
            <div>1'200.00 / Stk.</div>
        </li>
    </ul>
</body>
</html>
"""

SAMPLE_HTML_MULTIPLE_LISTINGS = """
<html>
<body>
    <ul class="product-list">
        <li>
            <h3><a href="/de/12345/sig-p226">SIG P226</a></h3>
            <img src="/images/gun1.jpg">
            <div>1'200.00 / Stk.</div>
        </li>
        <li>
            <h3><a href="/de/12346/glock-17">Glock 17 Gen5</a></h3>
            <img src="/images/gun2.jpg">
            <div>850.00 / Stk.</div>
        </li>
        <li>
            <h3><a href="/de/12347/cz-75">CZ 75 B</a></h3>
            <img src="/images/gun3.jpg">
            <div>CHF 750</div>
        </li>
    </ul>
</body>
</html>
"""

SAMPLE_HTML_NO_LISTINGS = """
<html>
<body>
    <div class="empty-state">
        <p>Keine Produkte gefunden</p>
    </div>
</body>
</html>
"""

SAMPLE_HTML_WITH_PAGINATION = """
<html>
<body>
    <ul class="product-list">
        <li>
            <h3><a href="/de/12345/test-gun">Test Gun</a></h3>
            <div>500.00 / Stk.</div>
        </li>
    </ul>
    <div class="pagination">
        <a href="?seite=1">1</a>
        <a href="?seite=2">2</a>
        <a href="?seite=3">3</a>
    </div>
</body>
</html>
"""

SAMPLE_HTML_MISSING_PRICE = """
<html>
<body>
    <ul class="product-list">
        <li>
            <h3><a href="/de/12345/sig-p226">SIG P226</a></h3>
            <img src="/images/gun1.jpg">
        </li>
    </ul>
</body>
</html>
"""


class TestScrapeAebiwaffen:
    """Tests for scrape_aebiwaffen main function."""

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

        with patch("backend.scrapers.aebiwaffen.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.aebiwaffen.delay_between_requests", new_callable=AsyncMock):
                with patch("backend.services.crawler.add_crawl_log"):
                    results = await scrape_aebiwaffen()

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

        with patch("backend.scrapers.aebiwaffen.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.aebiwaffen.delay_between_requests", new_callable=AsyncMock):
                with patch("backend.services.crawler.add_crawl_log"):
                    results = await scrape_aebiwaffen()

        assert len(results) == 3

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

        with patch("backend.scrapers.aebiwaffen.create_http_client", return_value=mock_client):
            with patch("backend.services.crawler.add_crawl_log"):
                results = await scrape_aebiwaffen()

        assert results == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_connection_error(self):
        """Test that connection errors return empty list."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.aebiwaffen.create_http_client", return_value=mock_client):
            with patch("backend.services.crawler.add_crawl_log"):
                results = await scrape_aebiwaffen()

        assert results == []


class TestExtractTitle:
    """Tests for _extract_title helper function."""

    def test_extracts_title_from_h3_a(self):
        """Extract title from h3 > a structure."""
        html = '<li><h3><a href="/de/123/gun">Test Gun</a></h3></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        assert _extract_title(listing) == "Test Gun"

    def test_extracts_title_from_h3(self):
        """Extract title from h3 element."""
        html = '<li><h3>Test Gun</h3></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        assert _extract_title(listing) == "Test Gun"

    def test_extracts_title_from_link(self):
        """Extract title from link with /de/ in href."""
        html = '<li><a href="/de/123/test-gun">Test Gun</a></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        assert _extract_title(listing) == "Test Gun"

    def test_returns_none_for_missing_title(self):
        """Return None when no title element found."""
        html = '<li><span>abc</span></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        assert _extract_title(listing) is None

    def test_skips_short_text(self):
        """Skip text that is too short."""
        html = '<li><h3>ab</h3></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        assert _extract_title(listing) is None


class TestExtractPrice:
    """Tests for _extract_price helper function."""

    def test_extracts_price_with_stk_format(self):
        """Extract price from Swiss format with / Stk."""
        html = "<li><div>1'200.00 / Stk.</div></li>"
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        assert _extract_price(listing) == 1200.0

    def test_extracts_price_with_chf(self):
        """Extract price with CHF prefix."""
        html = '<li><span>CHF 850.50</span></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        assert _extract_price(listing) == 850.5

    def test_extracts_price_with_fr(self):
        """Extract price with Fr. prefix."""
        html = "<li><span>Fr. 2'500.-</span></li>"
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        assert _extract_price(listing) == 2500.0

    def test_returns_none_for_missing_price(self):
        """Return None when no price found."""
        html = '<li><span>No price here</span></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        assert _extract_price(listing) is None

    def test_handles_unicode_apostrophe(self):
        """Handle Unicode apostrophe in price."""
        html = "<li><div>6\u2019950.00 / Stk.</div></li>"
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        assert _extract_price(listing) == 6950.0


class TestExtractLink:
    """Tests for _extract_link helper function."""

    def test_extracts_link_from_h3_a(self):
        """Extract link from h3 > a structure."""
        html = '<li><h3><a href="/de/12345/sig-p226">SIG P226</a></h3></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        link = _extract_link(listing)
        assert link == f"{BASE_URL}/de/12345/sig-p226"

    def test_extracts_link_with_de_path(self):
        """Extract link with /de/ in path."""
        html = '<li><a href="/de/123/test-gun">Test</a></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        link = _extract_link(listing)
        assert link == f"{BASE_URL}/de/123/test-gun"

    def test_returns_none_for_missing_link(self):
        """Return None when no valid link found."""
        html = '<li><span>No link</span></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        assert _extract_link(listing) is None

    def test_returns_none_for_non_product_link(self):
        """Return None for links without product ID pattern."""
        html = '<li><a href="/de/waffen/">Waffen</a></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        assert _extract_link(listing) is None


class TestExtractImageUrl:
    """Tests for _extract_image_url helper function."""

    def test_extracts_image_from_src(self):
        """Extract image URL from src attribute."""
        html = '<li><img src="/images/gun.jpg"></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        image_url = _extract_image_url(listing)
        assert image_url == f"{BASE_URL}/images/gun.jpg"

    def test_extracts_image_from_data_src(self):
        """Extract image URL from data-src attribute (lazy loading)."""
        html = '<li><img data-src="/images/lazy.jpg"></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        image_url = _extract_image_url(listing)
        assert image_url == f"{BASE_URL}/images/lazy.jpg"

    def test_returns_none_for_missing_image(self):
        """Return None when no image found."""
        html = '<li><span>No image</span></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        assert _extract_image_url(listing) is None

    def test_skips_placeholder_images(self):
        """Skip images that are placeholders."""
        html = '<li><img src="/images/placeholder.gif"></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        assert _extract_image_url(listing) is None


class TestHasNextPage:
    """Tests for _has_next_page helper function."""

    def test_detects_next_page_link(self):
        """Detect pagination with seite parameter."""
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
            <div class="pagination">
                <a href="?seite=1">1</a>
                <a href="?seite=2">2</a>
            </div>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        assert _has_next_page(soup, current_page=2) is False

    def test_detects_next_link(self):
        """Detect pagination via next class link."""
        html = """
        <html><body>
            <a class="next" href="?seite=2">Weiter</a>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        assert _has_next_page(soup, current_page=1) is True

    def test_detects_weiter_text(self):
        """Detect pagination via 'Weiter' text."""
        html = """
        <html><body>
            <a href="?seite=2">Weiter</a>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        assert _has_next_page(soup, current_page=1) is True


class TestParseListing:
    """Tests for _parse_listing helper function."""

    def test_parses_complete_listing(self):
        """Parse a listing with all fields."""
        html = """
        <li>
            <h3><a href="/de/12345/test-gun">Test Gun</a></h3>
            <img src="/images/gun.jpg">
            <div>1'000.00 / Stk.</div>
        </li>
        """
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        result = _parse_listing(listing)

        assert result is not None
        assert result["title"] == "Test Gun"
        assert result["price"] == 1000.0
        assert result["link"] == f"{BASE_URL}/de/12345/test-gun"
        assert result["image_url"] == f"{BASE_URL}/images/gun.jpg"
        assert result["source"] == SOURCE_NAME

    def test_returns_none_for_missing_title(self):
        """Return None when title is missing."""
        html = '<li><a href="/de/123/item"></a></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        result = _parse_listing(listing)
        assert result is None

    def test_returns_none_for_missing_link(self):
        """Return None when link is missing."""
        html = '<li><h3>Test</h3></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        result = _parse_listing(listing)
        assert result is None

    def test_handles_partial_data(self):
        """Handle listing with only required fields (title, link)."""
        html = """
        <li>
            <h3><a href="/de/12345/test-gun">Test Gun</a></h3>
        </li>
        """
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        result = _parse_listing(listing)

        assert result is not None
        assert result["title"] == "Test Gun"
        assert result["link"] == f"{BASE_URL}/de/12345/test-gun"
        assert result["price"] is None
        assert result["image_url"] is None
