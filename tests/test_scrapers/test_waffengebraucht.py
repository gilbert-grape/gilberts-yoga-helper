"""
Tests for waffengebraucht.ch scraper.

Tests verify:
- Successful extraction of listing data (title, price, image_url, link, source)
- Price extraction including "Auf Anfrage" handling
- Relative URL conversion to absolute
- Error handling returns empty list
- Logging on errors
- Multi-category scraping (kurzwaffen, langwaffen)
- Pagination across multiple pages
"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.scrapers.waffengebraucht import (
    BASE_URL,
    CATEGORY_URLS,
    SOURCE_NAME,
    scrape_waffengebraucht,
    _extract_image_url,
    _extract_link,
    _extract_price,
    _extract_title,
    _has_next_page,
    _parse_listing,
)
from bs4 import BeautifulSoup


# Sample HTML fixtures mimicking waffengebraucht.ch structure
SAMPLE_HTML_SINGLE_LISTING = """
<html>
<body>
    <div class="item">
        <a href="/zuerich/sig-p226-9mm/12345">
            <img src="/photo/default.png/520/325">
            <h3 class="title">SIG P226 9mm</h3>
            <span class="price">1'200CHF</span>
        </a>
    </div>
</body>
</html>
"""

SAMPLE_HTML_MULTIPLE_LISTINGS = """
<html>
<body>
    <div class="item">
        <a href="/zuerich/sig-p226-9mm/12345">
            <img src="/photo/gun1.jpg">
            <h3 class="title">SIG P226 9mm</h3>
            <span class="price">1'200CHF</span>
        </a>
    </div>
    <div class="item">
        <a href="/bern/glock-17-gen5/12346">
            <img src="/photo/gun2.jpg">
            <h3 class="title">Glock 17 Gen5</h3>
            <span class="price">850CHF VB</span>
        </a>
    </div>
    <div class="item">
        <a href="/basel/remington-870/12347">
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
    <div class="item">
        <a href="/zuerich/test-gun/12345">
            <h3 class="title">Test Gun</h3>
            <span class="price">500CHF</span>
        </a>
    </div>
    <div class="pagination">
        <a href="?&page=1">Erste</a>
        <a href="?&page=2">2</a>
        <a href="?&page=3">3</a>
        <a href="?&page=34">Letzte</a>
    </div>
</body>
</html>
"""

SAMPLE_HTML_RELATIVE_URLS = """
<html>
<body>
    <div class="item">
        <a href="/zuerich/test-item/12345">
            <img src="../photo/photo.jpg">
            <h3 class="title">Test Item</h3>
            <span class="price">100CHF</span>
        </a>
    </div>
</body>
</html>
"""

SAMPLE_HTML_MISSING_PRICE = """
<html>
<body>
    <div class="item">
        <a href="/zuerich/sig-p226/12345">
            <img src="/photo/gun1.jpg">
            <h3 class="title">SIG P226</h3>
        </a>
    </div>
</body>
</html>
"""

SAMPLE_HTML_MISSING_IMAGE = """
<html>
<body>
    <div class="item">
        <a href="/zuerich/sig-p226/12345">
            <h3 class="title">SIG P226</h3>
            <span class="price">1'200CHF</span>
        </a>
    </div>
</body>
</html>
"""

SAMPLE_HTML_ALT_STRUCTURE = """
<html>
<body>
    <article class="inserat">
        <a href="/bern/browning-hi-power/12348" class="detail-link">
            <img data-src="/photo/lazy.jpg">
            <h2>Browning Hi-Power</h2>
            <div class="preis">2.500CHF</div>
        </a>
    </article>
</body>
</html>
"""

SAMPLE_HTML_PRICE_VB = """
<html>
<body>
    <div class="item">
        <a href="/zuerich/glock-19/12349">
            <h3 class="title">Glock 19</h3>
            <span class="price">1.550CHF VB</span>
        </a>
    </div>
</body>
</html>
"""


class TestScrapeWaffengebraucht:
    """Tests for scrape_waffengebraucht main function."""

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

        with patch("backend.scrapers.waffengebraucht.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.waffengebraucht.delay_between_requests", new_callable=AsyncMock):
                results = await scrape_waffengebraucht()

        # One listing per category, but same HTML so we get 2 listings total
        assert len(results) >= 1
        assert results[0]["title"] == "SIG P226 9mm"
        assert results[0]["price"] == 1200.0
        assert results[0]["source"] == SOURCE_NAME
        assert "/sig-p226-9mm/12345" in results[0]["link"]

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

        with patch("backend.scrapers.waffengebraucht.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.waffengebraucht.delay_between_requests", new_callable=AsyncMock):
                results = await scrape_waffengebraucht()

        # 3 listings per category, 2 categories = 6 total
        assert len(results) >= 3
        titles = [r["title"] for r in results]
        assert "SIG P226 9mm" in titles
        assert "Glock 17 Gen5" in titles
        assert "Remington 870" in titles

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

        with patch("backend.scrapers.waffengebraucht.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.waffengebraucht.delay_between_requests", new_callable=AsyncMock):
                results = await scrape_waffengebraucht()

        # Find the Remington listing which has "Auf Anfrage"
        remington_listings = [r for r in results if "Remington" in r["title"]]
        assert len(remington_listings) > 0
        assert remington_listings[0]["price"] is None

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

        with patch("backend.scrapers.waffengebraucht.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.waffengebraucht.delay_between_requests", new_callable=AsyncMock):
                results = await scrape_waffengebraucht()

        assert len(results) >= 1
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

        with patch("backend.scrapers.waffengebraucht.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.waffengebraucht.delay_between_requests", new_callable=AsyncMock):
                results = await scrape_waffengebraucht()

        assert len(results) >= 1
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

        with patch("backend.scrapers.waffengebraucht.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.waffengebraucht.delay_between_requests", new_callable=AsyncMock):
                results = await scrape_waffengebraucht()

        assert len(results) >= 1
        # URLs should be absolute
        assert results[0]["link"].startswith("https://")
        if results[0]["image_url"]:
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

        with patch("backend.scrapers.waffengebraucht.create_http_client", return_value=mock_client):
            results = await scrape_waffengebraucht()

        assert results == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_connection_error(self):
        """Test that connection errors return empty list (AC: 5)."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.waffengebraucht.create_http_client", return_value=mock_client):
            results = await scrape_waffengebraucht()

        assert results == []

    @pytest.mark.asyncio
    async def test_logs_error_on_failure(self):
        """Test that errors are logged (AC: 5)."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Test error"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.waffengebraucht.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.waffengebraucht.logger") as mock_logger:
                results = await scrape_waffengebraucht()

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

        with patch("backend.scrapers.waffengebraucht.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.waffengebraucht.delay_between_requests", new_callable=AsyncMock):
                results = await scrape_waffengebraucht()

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

        with patch("backend.scrapers.waffengebraucht.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.waffengebraucht.delay_between_requests", new_callable=AsyncMock):
                results = await scrape_waffengebraucht()

        assert results[0]["source"] == "waffengebraucht.ch"

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

        with patch("backend.scrapers.waffengebraucht.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.waffengebraucht.delay_between_requests", new_callable=AsyncMock):
                results = await scrape_waffengebraucht()

        assert len(results) >= 1
        assert results[0]["title"] == "Browning Hi-Power"
        assert results[0]["price"] == 2500.0

    @pytest.mark.asyncio
    async def test_handles_price_with_vb_suffix(self):
        """Test that prices with VB (Verhandlungsbasis) suffix are parsed correctly."""
        mock_response = MagicMock()
        mock_response.text = SAMPLE_HTML_PRICE_VB
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.waffengebraucht.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.waffengebraucht.delay_between_requests", new_callable=AsyncMock):
                results = await scrape_waffengebraucht()

        assert len(results) >= 1
        assert results[0]["price"] == 1550.0

    @pytest.mark.asyncio
    async def test_scrapes_multiple_categories(self):
        """Test that scraper fetches from multiple category URLs."""
        mock_response = MagicMock()
        mock_response.text = SAMPLE_HTML_SINGLE_LISTING
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.waffengebraucht.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.waffengebraucht.delay_between_requests", new_callable=AsyncMock):
                await scrape_waffengebraucht()

        # Should have been called at least once per category
        assert mock_client.get.call_count >= len(CATEGORY_URLS)

    @pytest.mark.asyncio
    async def test_pagination_scrapes_multiple_pages(self):
        """Test that scraper handles pagination correctly across multiple pages."""
        page1_html = """
        <html>
        <body>
            <div class="item">
                <a href="/zuerich/gun-1/1"><h3 class="title">Gun 1</h3><span class="price">100CHF</span></a>
            </div>
            <div class="pagination">
                <a href="?&page=1">Erste</a>
                <a href="?&page=2">2</a>
                <a href="?&page=3">Letzte</a>
            </div>
        </body>
        </html>
        """
        page2_html = """
        <html>
        <body>
            <div class="item">
                <a href="/zuerich/gun-2/2"><h3 class="title">Gun 2</h3><span class="price">200CHF</span></a>
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

        # Simulate: page1 for kurzwaffen, page2 for kurzwaffen, page1 for langwaffen (no pagination)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            mock_response_page1, mock_response_page2,  # kurzwaffen pages
            mock_response_page2  # langwaffen (same response, no pagination)
        ])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.waffengebraucht.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.waffengebraucht.delay_between_requests", new_callable=AsyncMock):
                results = await scrape_waffengebraucht()

        # Should have listings from multiple pages
        titles = [r["title"] for r in results]
        assert "Gun 1" in titles
        assert "Gun 2" in titles


class TestExtractTitle:
    """Tests for _extract_title helper function."""

    def test_extracts_title_from_title_class(self):
        """Extract title from element with class 'title'."""
        html = '<div class="item"><h3 class="title">Test Gun</h3></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".item")
        assert _extract_title(listing) == "Test Gun"

    def test_extracts_title_from_h2(self):
        """Extract title from h2 element."""
        html = '<div class="item"><h2>Test Gun</h2></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".item")
        assert _extract_title(listing) == "Test Gun"

    def test_extracts_title_from_h3(self):
        """Extract title from h3 element."""
        html = '<div class="item"><h3>Test Gun</h3></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".item")
        assert _extract_title(listing) == "Test Gun"

    def test_extracts_title_from_link_text(self):
        """Extract title from anchor text when no specific title element."""
        html = '<div class="item"><a href="/test/item/123">My Gun Title</a></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".item")
        assert _extract_title(listing) == "My Gun Title"

    def test_returns_none_for_empty_listing(self):
        """Return None when listing has no content."""
        html = '<div class="item"></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".item")
        result = _extract_title(listing)
        assert result is None


class TestExtractPrice:
    """Tests for _extract_price helper function."""

    def test_extracts_price_from_price_class(self):
        """Extract price from element with class 'price'."""
        html = '<div class="item"><span class="price">1\'200CHF</span></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".item")
        assert _extract_price(listing) == 1200.0

    def test_extracts_price_with_decimals(self):
        """Extract price with decimal value."""
        html = '<div class="item"><span class="price">850.50CHF</span></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".item")
        assert _extract_price(listing) == 850.5

    def test_extracts_price_with_dot_thousands_separator(self):
        """Extract price using dot as thousands separator (1.550CHF)."""
        html = '<div class="item"><span class="price">1.550CHF</span></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".item")
        assert _extract_price(listing) == 1550.0

    def test_returns_none_for_auf_anfrage(self):
        """Return None for 'Auf Anfrage'."""
        html = '<div class="item"><span class="price">Auf Anfrage</span></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".item")
        assert _extract_price(listing) is None

    def test_returns_none_for_missing_price(self):
        """Return None when no price element found."""
        html = '<div class="item"><span>No price</span></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".item")
        assert _extract_price(listing) is None

    def test_extracts_price_from_preis_class(self):
        """Extract price from element with class 'preis' (German)."""
        html = '<div class="item"><div class="preis">2\'500CHF</div></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".item")
        assert _extract_price(listing) == 2500.0

    def test_extracts_price_from_text_with_chf(self):
        """Extract price from text containing CHF."""
        html = '<div class="item">Some text 500CHF more text</div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".item")
        assert _extract_price(listing) == 500.0

    def test_handles_price_with_vb_suffix(self):
        """Handle prices with VB (Verhandlungsbasis) suffix."""
        html = '<div class="item"><span class="price">1.550CHF VB</span></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".item")
        assert _extract_price(listing) == 1550.0


class TestExtractLink:
    """Tests for _extract_link helper function."""

    def test_extracts_link_with_location_pattern(self):
        """Extract link matching /location/item/id pattern."""
        html = '<div class="item"><a href="/zuerich/sig-p226/12345">Link</a></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".item")
        link = _extract_link(listing)
        assert link == f"{BASE_URL}/zuerich/sig-p226/12345"

    def test_converts_relative_link_to_absolute(self):
        """Convert relative link to absolute URL."""
        html = '<div class="item"><a href="/bern/glock-17/12346">Link</a></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".item")
        link = _extract_link(listing)
        assert link.startswith("https://")

    def test_returns_none_for_missing_link(self):
        """Return None when no link found."""
        html = '<div class="item"><span>No link</span></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".item")
        assert _extract_link(listing) is None

    def test_handles_absolute_url(self):
        """Handle already absolute URLs."""
        html = '<div class="item"><a href="https://www.waffengebraucht.ch/test/item/123">Link</a></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".item")
        link = _extract_link(listing)
        assert link == "https://www.waffengebraucht.ch/test/item/123"


class TestExtractImageUrl:
    """Tests for _extract_image_url helper function."""

    def test_extracts_image_from_src(self):
        """Extract image URL from src attribute."""
        html = '<div class="item"><img src="/photo/gun.jpg"></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".item")
        image_url = _extract_image_url(listing)
        assert image_url == f"{BASE_URL}/photo/gun.jpg"

    def test_extracts_image_from_data_src(self):
        """Extract image URL from data-src attribute (lazy loading)."""
        html = '<div class="item"><img data-src="/photo/lazy.jpg"></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".item")
        image_url = _extract_image_url(listing)
        assert image_url == f"{BASE_URL}/photo/lazy.jpg"

    def test_returns_none_for_missing_image(self):
        """Return None when no image found."""
        html = '<div class="item"><span>No image</span></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".item")
        assert _extract_image_url(listing) is None

    def test_skips_placeholder_images(self):
        """Skip images that are placeholders."""
        html = '<div class="item"><img src="/images/placeholder.gif"></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".item")
        assert _extract_image_url(listing) is None


class TestHasNextPage:
    """Tests for _has_next_page helper function."""

    def test_detects_pagination_with_page_links(self):
        """Detect pagination with page parameter links."""
        soup = BeautifulSoup(SAMPLE_HTML_WITH_PAGINATION, "lxml")
        assert _has_next_page(soup) is True

    def test_returns_false_for_no_pagination(self):
        """Return False when no pagination found."""
        soup = BeautifulSoup(SAMPLE_HTML_NO_LISTINGS, "lxml")
        assert _has_next_page(soup) is False

    def test_detects_letzte_link(self):
        """Detect pagination via 'Letzte' (Last) link."""
        html = """
        <html><body>
            <a href="?&page=10">Letzte</a>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        assert _has_next_page(soup) is True


class TestParseListing:
    """Tests for _parse_listing helper function."""

    def test_parses_complete_listing(self):
        """Parse a listing with all fields."""
        html = """
        <div class="item">
            <a href="/zuerich/test-gun/12345">
                <img src="/photo/gun.jpg">
                <h3 class="title">Test Gun</h3>
                <span class="price">1'000CHF</span>
            </a>
        </div>
        """
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".item")
        result = _parse_listing(listing)

        assert result is not None
        assert result["title"] == "Test Gun"
        assert result["price"] == 1000.0
        assert "/test-gun/12345" in result["link"]
        assert result["image_url"] == f"{BASE_URL}/photo/gun.jpg"
        assert result["source"] == SOURCE_NAME

    def test_returns_none_for_missing_title(self):
        """Return None when title is missing."""
        html = '<div class="item"><a href="/zuerich/item/12345"></a></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".item")
        result = _parse_listing(listing)
        assert result is None

    def test_returns_none_for_missing_link(self):
        """Return None when link is missing."""
        html = '<div class="item"><h3 class="title">Test</h3></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".item")
        result = _parse_listing(listing)
        assert result is None

    def test_handles_partial_data(self):
        """Handle listing with only required fields (title, link)."""
        html = """
        <div class="item">
            <a href="/zuerich/test-gun/12345">
                <h3 class="title">Test Gun</h3>
            </a>
        </div>
        """
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".item")
        result = _parse_listing(listing)

        assert result is not None
        assert result["title"] == "Test Gun"
        assert "/test-gun/12345" in result["link"]
        assert result["price"] is None
        assert result["image_url"] is None
