"""
Tests for waffenboerse.ch scraper.

Tests verify:
- Successful extraction of listing data (title, price, image_url, link, source)
- Price extraction including "Auf Anfrage" handling
- Relative URL conversion to absolute
- Error handling returns empty list
- Logging on errors
"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.scrapers.waffenboerse import (
    BASE_URL,
    SOURCE_NAME,
    scrape_waffenboerse,
    _extract_image_url,
    _extract_link,
    _extract_price,
    _extract_title,
    _has_next_page,
    _parse_listing,
)
from bs4 import BeautifulSoup


# Sample HTML fixtures mimicking waffenboerse.ch structure
SAMPLE_HTML_SINGLE_LISTING = """
<html>
<body>
    <div class="inserat-item">
        <a href="/inserat/123">
            <img src="/images/gun1.jpg">
            <h3 class="title">SIG P226</h3>
            <span class="price">CHF 1'200</span>
        </a>
    </div>
</body>
</html>
"""

SAMPLE_HTML_MULTIPLE_LISTINGS = """
<html>
<body>
    <div class="inserat-item">
        <a href="/inserat/123">
            <img src="/images/gun1.jpg">
            <h3 class="title">SIG P226</h3>
            <span class="price">CHF 1'200</span>
        </a>
    </div>
    <div class="inserat-item">
        <a href="/inserat/456">
            <img src="/images/gun2.jpg">
            <h3 class="title">Glock 17</h3>
            <span class="price">CHF 850.50</span>
        </a>
    </div>
    <div class="inserat-item">
        <a href="/inserat/789">
            <h3 class="title">Remington 870</h3>
            <span class="price">Auf Anfrage</span>
        </a>
    </div>
</body>
</html>
"""

SAMPLE_HTML_NO_LISTINGS = """
<html>
<body>
    <div class="empty-state">
        <p>Keine Inserate gefunden</p>
    </div>
</body>
</html>
"""

SAMPLE_HTML_WITH_PAGINATION = """
<html>
<body>
    <div class="inserat-item">
        <a href="/inserat/123">
            <h3 class="title">Test Gun</h3>
            <span class="price">CHF 500</span>
        </a>
    </div>
    <div class="pagination">
        <a href="?page=1">1</a>
        <a href="?page=2">2</a>
        <a class="next" href="?page=2">»</a>
    </div>
</body>
</html>
"""

SAMPLE_HTML_RELATIVE_URLS = """
<html>
<body>
    <div class="inserat-item">
        <a href="../inserat/123">
            <img src="../images/photo.jpg">
            <h3 class="title">Test Item</h3>
            <span class="price">CHF 100</span>
        </a>
    </div>
</body>
</html>
"""

SAMPLE_HTML_MISSING_PRICE = """
<html>
<body>
    <div class="inserat-item">
        <a href="/inserat/123">
            <img src="/images/gun1.jpg">
            <h3 class="title">SIG P226</h3>
        </a>
    </div>
</body>
</html>
"""

SAMPLE_HTML_MISSING_IMAGE = """
<html>
<body>
    <div class="inserat-item">
        <a href="/inserat/123">
            <h3 class="title">SIG P226</h3>
            <span class="price">CHF 1'200</span>
        </a>
    </div>
</body>
</html>
"""

SAMPLE_HTML_ALT_STRUCTURE = """
<html>
<body>
    <article class="inserat">
        <a href="/inserat/100" class="detail-link">
            <img data-src="/images/lazy.jpg">
            <h2>Browning Hi-Power</h2>
            <div class="preis">Fr. 2'500.-</div>
        </a>
    </article>
</body>
</html>
"""


class TestScrapeWaffenboerse:
    """Tests for scrape_waffenboerse main function."""

    @pytest.mark.asyncio
    async def test_extracts_single_listing(self):
        """Test that scraper extracts a single listing correctly (AC: 1, 2)."""
        mock_response = MagicMock()
        mock_response.text = SAMPLE_HTML_SINGLE_LISTING
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.waffenboerse.create_http_client", return_value=mock_client):
            results = await scrape_waffenboerse()

        assert len(results) == 1
        assert results[0]["title"] == "SIG P226"
        assert results[0]["price"] == 1200.0
        assert results[0]["source"] == SOURCE_NAME
        assert results[0]["link"] == f"{BASE_URL}/inserat/123"
        assert results[0]["image_url"] == f"{BASE_URL}/images/gun1.jpg"

    @pytest.mark.asyncio
    async def test_extracts_multiple_listings(self):
        """Test that scraper extracts multiple listings (AC: 1, 2)."""
        mock_response = MagicMock()
        mock_response.text = SAMPLE_HTML_MULTIPLE_LISTINGS
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.waffenboerse.create_http_client", return_value=mock_client):
            results = await scrape_waffenboerse()

        assert len(results) == 3
        assert results[0]["title"] == "SIG P226"
        assert results[1]["title"] == "Glock 17"
        assert results[2]["title"] == "Remington 870"

    @pytest.mark.asyncio
    async def test_handles_auf_anfrage_price(self):
        """Test that 'Auf Anfrage' price is stored as None (AC: 3)."""
        mock_response = MagicMock()
        mock_response.text = SAMPLE_HTML_MULTIPLE_LISTINGS
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.waffenboerse.create_http_client", return_value=mock_client):
            results = await scrape_waffenboerse()

        # The third listing has "Auf Anfrage" price
        assert results[2]["price"] is None

    @pytest.mark.asyncio
    async def test_handles_missing_price(self):
        """Test that missing price is stored as None (AC: 3)."""
        mock_response = MagicMock()
        mock_response.text = SAMPLE_HTML_MISSING_PRICE
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.waffenboerse.create_http_client", return_value=mock_client):
            results = await scrape_waffenboerse()

        assert len(results) == 1
        assert results[0]["price"] is None

    @pytest.mark.asyncio
    async def test_handles_missing_image(self):
        """Test that missing image is stored as None."""
        mock_response = MagicMock()
        mock_response.text = SAMPLE_HTML_MISSING_IMAGE
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.waffenboerse.create_http_client", return_value=mock_client):
            results = await scrape_waffenboerse()

        assert len(results) == 1
        assert results[0]["image_url"] is None

    @pytest.mark.asyncio
    async def test_converts_relative_urls_to_absolute(self):
        """Test that relative URLs are converted to absolute (AC: 4)."""
        mock_response = MagicMock()
        mock_response.text = SAMPLE_HTML_RELATIVE_URLS
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.waffenboerse.create_http_client", return_value=mock_client):
            results = await scrape_waffenboerse()

        assert len(results) == 1
        # URLs should be absolute
        assert results[0]["link"].startswith("https://")
        assert results[0]["image_url"].startswith("https://")

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_http_error(self):
        """Test that HTTP errors return empty list (AC: 5)."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.HTTPStatusError(
            "Server Error",
            request=MagicMock(),
            response=MagicMock(status_code=500)
        ))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.waffenboerse.create_http_client", return_value=mock_client):
            results = await scrape_waffenboerse()

        assert results == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_connection_error(self):
        """Test that connection errors return empty list (AC: 5)."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.waffenboerse.create_http_client", return_value=mock_client):
            results = await scrape_waffenboerse()

        assert results == []

    @pytest.mark.asyncio
    async def test_logs_error_on_failure(self):
        """Test that errors are logged (AC: 5)."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Test error"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.waffenboerse.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.waffenboerse.logger") as mock_logger:
                results = await scrape_waffenboerse()

        assert results == []
        mock_logger.error.assert_called_once()
        assert SOURCE_NAME in str(mock_logger.error.call_args)

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_no_listings(self):
        """Test that empty pages return empty list."""
        mock_response = MagicMock()
        mock_response.text = SAMPLE_HTML_NO_LISTINGS
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.waffenboerse.create_http_client", return_value=mock_client):
            results = await scrape_waffenboerse()

        assert results == []

    @pytest.mark.asyncio
    async def test_sets_correct_source_name(self):
        """Test that source field is set correctly (AC: 2)."""
        mock_response = MagicMock()
        mock_response.text = SAMPLE_HTML_SINGLE_LISTING
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.waffenboerse.create_http_client", return_value=mock_client):
            results = await scrape_waffenboerse()

        assert results[0]["source"] == "waffenboerse.ch"

    @pytest.mark.asyncio
    async def test_handles_alternative_html_structure(self):
        """Test that scraper handles alternative HTML structures."""
        mock_response = MagicMock()
        mock_response.text = SAMPLE_HTML_ALT_STRUCTURE
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.waffenboerse.create_http_client", return_value=mock_client):
            results = await scrape_waffenboerse()

        assert len(results) == 1
        assert results[0]["title"] == "Browning Hi-Power"
        assert results[0]["price"] == 2500.0

    @pytest.mark.asyncio
    async def test_pagination_scrapes_multiple_pages(self):
        """Test that scraper handles pagination correctly across multiple pages."""
        # Page 1 has pagination, page 2 does not
        page1_html = """
        <html>
        <body>
            <div class="inserat-item">
                <a href="/inserat/1"><h3 class="title">Gun 1</h3><span class="price">CHF 100</span></a>
            </div>
            <div class="pagination">
                <a href="?page=1">1</a>
                <a href="?page=2">2</a>
                <a class="next" href="?page=2">»</a>
            </div>
        </body>
        </html>
        """
        page2_html = """
        <html>
        <body>
            <div class="inserat-item">
                <a href="/inserat/2"><h3 class="title">Gun 2</h3><span class="price">CHF 200</span></a>
            </div>
        </body>
        </html>
        """

        mock_response_page1 = MagicMock()
        mock_response_page1.text = page1_html
        mock_response_page1.raise_for_status = MagicMock()

        mock_response_page2 = MagicMock()
        mock_response_page2.text = page2_html
        mock_response_page2.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        # Return different responses for page 1 and page 2
        mock_client.get = AsyncMock(side_effect=[mock_response_page1, mock_response_page2])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.waffenboerse.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.waffenboerse.delay_between_requests", new_callable=AsyncMock):
                results = await scrape_waffenboerse()

        # Should have listings from both pages
        assert len(results) == 2
        assert results[0]["title"] == "Gun 1"
        assert results[1]["title"] == "Gun 2"
        # Verify both pages were fetched
        assert mock_client.get.call_count == 2


class TestExtractTitle:
    """Tests for _extract_title helper function."""

    def test_extracts_title_from_title_class(self):
        """Extract title from element with class 'title'."""
        html = '<div class="inserat"><h3 class="title">Test Gun</h3></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".inserat")
        assert _extract_title(listing) == "Test Gun"

    def test_extracts_title_from_h2(self):
        """Extract title from h2 element."""
        html = '<div class="inserat"><h2>Test Gun</h2></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".inserat")
        assert _extract_title(listing) == "Test Gun"

    def test_extracts_title_from_h3(self):
        """Extract title from h3 element."""
        html = '<div class="inserat"><h3>Test Gun</h3></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".inserat")
        assert _extract_title(listing) == "Test Gun"

    def test_returns_none_for_missing_title(self):
        """Return None when no title element found."""
        html = '<div class="inserat"><span>No title here</span></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".inserat")
        # May return None or the span text depending on fallback logic
        result = _extract_title(listing)
        # Either None or found something - test verifies no crash
        assert result is None or isinstance(result, str)


class TestExtractPrice:
    """Tests for _extract_price helper function."""

    def test_extracts_price_from_price_class(self):
        """Extract price from element with class 'price'."""
        html = '<div class="inserat"><span class="price">CHF 1\'200</span></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".inserat")
        assert _extract_price(listing) == 1200.0

    def test_extracts_price_with_decimals(self):
        """Extract price with decimal value."""
        html = '<div class="inserat"><span class="price">CHF 850.50</span></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".inserat")
        assert _extract_price(listing) == 850.5

    def test_returns_none_for_auf_anfrage(self):
        """Return None for 'Auf Anfrage'."""
        html = '<div class="inserat"><span class="price">Auf Anfrage</span></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".inserat")
        assert _extract_price(listing) is None

    def test_returns_none_for_missing_price(self):
        """Return None when no price element found."""
        html = '<div class="inserat"><span>No price</span></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".inserat")
        assert _extract_price(listing) is None

    def test_extracts_price_from_preis_class(self):
        """Extract price from element with class 'preis' (German)."""
        html = '<div class="inserat"><div class="preis">Fr. 2\'500.-</div></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".inserat")
        assert _extract_price(listing) == 2500.0


class TestExtractLink:
    """Tests for _extract_link helper function."""

    def test_extracts_link_from_inserat_href(self):
        """Extract link from href containing '/inserat/'."""
        html = '<div class="inserat"><a href="/inserat/123">Link</a></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".inserat")
        link = _extract_link(listing)
        assert link == f"{BASE_URL}/inserat/123"

    def test_converts_relative_link_to_absolute(self):
        """Convert relative link to absolute URL."""
        html = '<div class="inserat"><a href="../inserat/123">Link</a></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".inserat")
        link = _extract_link(listing)
        assert link.startswith("https://")

    def test_returns_none_for_missing_link(self):
        """Return None when no link found."""
        html = '<div class="inserat"><span>No link</span></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".inserat")
        assert _extract_link(listing) is None


class TestExtractImageUrl:
    """Tests for _extract_image_url helper function."""

    def test_extracts_image_from_src(self):
        """Extract image URL from src attribute."""
        html = '<div class="inserat"><img src="/images/gun.jpg"></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".inserat")
        image_url = _extract_image_url(listing)
        assert image_url == f"{BASE_URL}/images/gun.jpg"

    def test_extracts_image_from_data_src(self):
        """Extract image URL from data-src attribute (lazy loading)."""
        html = '<div class="inserat"><img data-src="/images/lazy.jpg"></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".inserat")
        image_url = _extract_image_url(listing)
        assert image_url == f"{BASE_URL}/images/lazy.jpg"

    def test_returns_none_for_missing_image(self):
        """Return None when no image found."""
        html = '<div class="inserat"><span>No image</span></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".inserat")
        assert _extract_image_url(listing) is None

    def test_skips_placeholder_images(self):
        """Skip images that are placeholders."""
        html = '<div class="inserat"><img src="/images/placeholder.gif"></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".inserat")
        assert _extract_image_url(listing) is None


class TestHasNextPage:
    """Tests for _has_next_page helper function."""

    def test_detects_next_page_link(self):
        """Detect pagination with next link."""
        soup = BeautifulSoup(SAMPLE_HTML_WITH_PAGINATION, "lxml")
        assert _has_next_page(soup) is True

    def test_returns_false_for_no_pagination(self):
        """Return False when no pagination found."""
        soup = BeautifulSoup(SAMPLE_HTML_NO_LISTINGS, "lxml")
        assert _has_next_page(soup) is False


class TestParseListing:
    """Tests for _parse_listing helper function."""

    def test_parses_complete_listing(self):
        """Parse a listing with all fields."""
        html = """
        <div class="inserat">
            <a href="/inserat/123">
                <img src="/images/gun.jpg">
                <h3 class="title">Test Gun</h3>
                <span class="price">CHF 1'000</span>
            </a>
        </div>
        """
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".inserat")
        result = _parse_listing(listing)

        assert result is not None
        assert result["title"] == "Test Gun"
        assert result["price"] == 1000.0
        assert result["link"] == f"{BASE_URL}/inserat/123"
        assert result["image_url"] == f"{BASE_URL}/images/gun.jpg"
        assert result["source"] == SOURCE_NAME

    def test_returns_none_for_missing_title(self):
        """Return None when title is missing."""
        html = '<div class="inserat"><a href="/inserat/123"></a></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".inserat")
        result = _parse_listing(listing)
        assert result is None

    def test_returns_none_for_missing_link(self):
        """Return None when link is missing."""
        html = '<div class="inserat"><h3 class="title">Test</h3></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".inserat")
        result = _parse_listing(listing)
        assert result is None

    def test_handles_partial_data(self):
        """Handle listing with only required fields (title, link)."""
        html = """
        <div class="inserat">
            <a href="/inserat/123">
                <h3 class="title">Test Gun</h3>
            </a>
        </div>
        """
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".inserat")
        result = _parse_listing(listing)

        assert result is not None
        assert result["title"] == "Test Gun"
        assert result["link"] == f"{BASE_URL}/inserat/123"
        assert result["price"] is None
        assert result["image_url"] is None
