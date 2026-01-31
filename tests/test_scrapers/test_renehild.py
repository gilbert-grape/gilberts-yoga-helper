"""
Tests for renehild-tactical.ch scraper.

Tests verify:
- Successful extraction of listing data (title, price, image_url, link, source)
- Price extraction including Swiss format with CHF
- WooCommerce-style pagination
- Error handling returns empty list
"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.scrapers.renehild import (
    BASE_URL,
    SOURCE_NAME,
    scrape_renehild,
    _extract_image_url,
    _extract_link,
    _extract_price,
    _extract_title,
    _has_next_page,
    _parse_listing,
)
from bs4 import BeautifulSoup


# Sample HTML fixtures mimicking renehild-tactical.ch WooCommerce structure
SAMPLE_HTML_SINGLE_LISTING = """
<html>
<body>
    <ul class="products">
        <li class="product">
            <a href="/produkt/sig-p226/" class="woocommerce-LoopProduct-link">
                <img src="/images/sig-p226.jpg">
                <h2 class="woocommerce-loop-product__title">SIG Sauer P226</h2>
                <span class="price"><bdi>CHF 1'200.00</bdi></span>
            </a>
        </li>
    </ul>
</body>
</html>
"""

SAMPLE_HTML_MULTIPLE_LISTINGS = """
<html>
<body>
    <ul class="products">
        <li class="product">
            <a href="/produkt/sig-p226/">
                <img src="/images/sig-p226.jpg">
                <h2 class="woocommerce-loop-product__title">SIG P226</h2>
                <span class="price"><bdi>CHF 1'200.00</bdi></span>
            </a>
        </li>
        <li class="product">
            <a href="/produkt/glock-17/">
                <img src="/images/glock-17.jpg">
                <h2 class="woocommerce-loop-product__title">Glock 17 Gen5</h2>
                <span class="price"><bdi>CHF 850.00</bdi></span>
            </a>
        </li>
        <li class="product">
            <a href="/produkt/cz-75/">
                <img src="/images/cz-75.jpg">
                <h2 class="woocommerce-loop-product__title">CZ 75 B</h2>
                <span class="price"><bdi>CHF 750.00</bdi></span>
            </a>
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
    <ul class="products">
        <li class="product">
            <a href="/produkt/test-gun/">
                <h2 class="woocommerce-loop-product__title">Test Gun</h2>
                <span class="price"><bdi>CHF 500.00</bdi></span>
            </a>
        </li>
    </ul>
    <nav class="woocommerce-pagination">
        <a href="/produkt-kategorie/waffenboerse/page/1/">1</a>
        <a href="/produkt-kategorie/waffenboerse/page/2/">2</a>
        <a href="/produkt-kategorie/waffenboerse/page/3/">3</a>
        <a class="next" href="/produkt-kategorie/waffenboerse/page/2/">→</a>
    </nav>
</body>
</html>
"""


class TestScrapeRenehild:
    """Tests for scrape_renehild main function."""

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

        with patch("backend.scrapers.renehild.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.renehild.delay_between_requests", new_callable=AsyncMock):
                with patch("backend.services.crawler.add_crawl_log"):
                    results = await scrape_renehild()

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

        with patch("backend.scrapers.renehild.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.renehild.delay_between_requests", new_callable=AsyncMock):
                with patch("backend.services.crawler.add_crawl_log"):
                    results = await scrape_renehild()

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

        with patch("backend.scrapers.renehild.create_http_client", return_value=mock_client):
            with patch("backend.services.crawler.add_crawl_log"):
                results = await scrape_renehild()

        assert results == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_connection_error(self):
        """Test that connection errors return empty list."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.renehild.create_http_client", return_value=mock_client):
            with patch("backend.services.crawler.add_crawl_log"):
                results = await scrape_renehild()

        assert results == []


class TestExtractTitle:
    """Tests for _extract_title helper function."""

    def test_extracts_title_from_woocommerce_class(self):
        """Extract title from WooCommerce product title class."""
        html = '<li><h2 class="woocommerce-loop-product__title">Test Gun</h2></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        assert _extract_title(listing) == "Test Gun"

    def test_extracts_title_from_h2(self):
        """Extract title from h2 element."""
        html = '<li><h2>Test Gun</h2></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        assert _extract_title(listing) == "Test Gun"

    def test_extracts_title_from_product_link(self):
        """Extract title from product link."""
        html = '<li><a href="/produkt/test-gun/">Test Gun Name</a></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        assert _extract_title(listing) == "Test Gun Name"

    def test_returns_none_for_missing_title(self):
        """Return None when no title element found."""
        html = '<li><span>abc</span></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        assert _extract_title(listing) is None

    def test_skips_short_text(self):
        """Skip text that is too short."""
        html = '<li><h2>ab</h2></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        assert _extract_title(listing) is None

    def test_skips_warenkorb_text(self):
        """Skip text containing Warenkorb (add to cart)."""
        html = '<li><h2>Real Title</h2><a href="/produkt/item/">In den Warenkorb</a></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        assert _extract_title(listing) == "Real Title"


class TestExtractPrice:
    """Tests for _extract_price helper function."""

    def test_extracts_price_from_bdi(self):
        """Extract price from WooCommerce bdi element."""
        html = '<li><span class="price"><bdi>CHF 1\'200.00</bdi></span></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        assert _extract_price(listing) == 1200.0

    def test_extracts_price_from_price_class(self):
        """Extract price from price class."""
        html = '<li><span class="price">CHF 850.50</span></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        assert _extract_price(listing) == 850.5

    def test_extracts_price_from_strong(self):
        """Extract price from strong element."""
        html = '<li><strong>CHF 750.00</strong></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        assert _extract_price(listing) == 750.0

    def test_extracts_price_from_full_text(self):
        """Extract price from full listing text."""
        html = '<li><div>Some product CHF 500.00 available</div></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        assert _extract_price(listing) == 500.0

    def test_returns_none_for_missing_price(self):
        """Return None when no price found."""
        html = '<li><span>No price here</span></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        assert _extract_price(listing) is None

    def test_handles_unicode_apostrophe(self):
        """Handle Unicode apostrophe in price."""
        html = "<li><span class='price'>CHF 6\u2019950.00</span></li>"
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        assert _extract_price(listing) == 6950.0


class TestExtractLink:
    """Tests for _extract_link helper function."""

    def test_extracts_link_from_woocommerce_class(self):
        """Extract link from WooCommerce product link class."""
        html = '<li><a class="woocommerce-LoopProduct-link" href="/produkt/sig-p226/">SIG</a></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        link = _extract_link(listing)
        assert link == f"{BASE_URL}/produkt/sig-p226/"

    def test_extracts_link_from_produkt_href(self):
        """Extract link with /produkt/ in href."""
        html = '<li><a href="/produkt/test-gun/">Test</a></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        link = _extract_link(listing)
        assert link == f"{BASE_URL}/produkt/test-gun/"

    def test_returns_none_for_missing_link(self):
        """Return None when no valid link found."""
        html = '<li><span>No link</span></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        assert _extract_link(listing) is None

    def test_returns_none_for_non_product_link(self):
        """Return None for links without /produkt/ path."""
        html = '<li><a href="/kategorie/waffen/">Waffen</a></li>'
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

    def test_extracts_image_from_srcset(self):
        """Extract image URL from srcset attribute."""
        html = '<li><img srcset="/images/gun-300.jpg 300w, /images/gun-600.jpg 600w"></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        image_url = _extract_image_url(listing)
        assert image_url == f"{BASE_URL}/images/gun-300.jpg"

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
        """Detect pagination with page/N/ pattern."""
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
            <nav class="woocommerce-pagination">
                <a href="/page/1/">1</a>
                <a href="/page/2/">2</a>
            </nav>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        assert _has_next_page(soup, current_page=2) is False

    def test_detects_next_class_link(self):
        """Detect pagination via next class link."""
        html = """
        <html><body>
            <a class="next" href="/page/2/">→</a>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        assert _has_next_page(soup, current_page=1) is True


class TestParseListing:
    """Tests for _parse_listing helper function."""

    def test_parses_complete_listing(self):
        """Parse a listing with all fields."""
        html = """
        <li class="product">
            <a href="/produkt/test-gun/">
                <img src="/images/gun.jpg">
                <h2 class="woocommerce-loop-product__title">Test Gun</h2>
                <span class="price"><bdi>CHF 1'000.00</bdi></span>
            </a>
        </li>
        """
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        result = _parse_listing(listing)

        assert result is not None
        assert result["title"] == "Test Gun"
        assert result["price"] == 1000.0
        assert result["link"] == f"{BASE_URL}/produkt/test-gun/"
        assert result["image_url"] == f"{BASE_URL}/images/gun.jpg"
        assert result["source"] == SOURCE_NAME

    def test_returns_none_for_missing_title(self):
        """Return None when title is missing."""
        html = '<li><a href="/produkt/item/"></a></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        result = _parse_listing(listing)
        assert result is None

    def test_returns_none_for_missing_link(self):
        """Return None when link is missing."""
        html = '<li><h2>Test</h2></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        result = _parse_listing(listing)
        assert result is None

    def test_handles_partial_data(self):
        """Handle listing with only required fields (title, link)."""
        html = """
        <li class="product">
            <a href="/produkt/test-gun/">
                <h2 class="woocommerce-loop-product__title">Test Gun</h2>
            </a>
        </li>
        """
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("li")
        result = _parse_listing(listing)

        assert result is not None
        assert result["title"] == "Test Gun"
        assert result["link"] == f"{BASE_URL}/produkt/test-gun/"
        assert result["price"] is None
        assert result["image_url"] is None
