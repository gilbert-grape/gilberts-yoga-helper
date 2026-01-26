"""
Tests for waffenzimmi.ch scraper.

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

from backend.scrapers.waffenzimmi import (
    BASE_URL,
    CATEGORY_URLS,
    SOURCE_NAME,
    scrape_waffenzimmi,
    _extract_image_url,
    _extract_link,
    _extract_price,
    _extract_title,
    _has_next_page,
    _parse_listing,
)
from bs4 import BeautifulSoup


# Sample HTML fixtures mimicking waffenzimmi.ch WooCommerce structure
SAMPLE_HTML_SINGLE_LISTING = """
<html>
<body>
    <ul class="products">
        <li class="product type-product">
            <a href="/produkt/sig-p226-9mm/" class="woocommerce-LoopProduct-link">
                <img src="/wp-content/uploads/2024/01/sig-p226.jpg" class="wp-post-image">
                <h2 class="woocommerce-loop-product__title">SIG P226 9mm</h2>
                <span class="price"><span class="woocommerce-Price-amount">CHF 1'200.00</span></span>
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
        <li class="product type-product">
            <a href="/produkt/sig-p226-9mm/" class="woocommerce-LoopProduct-link">
                <img src="/wp-content/uploads/gun1.jpg" class="wp-post-image">
                <h2 class="woocommerce-loop-product__title">SIG P226 9mm</h2>
                <span class="price"><span class="woocommerce-Price-amount">CHF 1'200.00</span></span>
            </a>
        </li>
        <li class="product type-product">
            <a href="/produkt/glock-17-gen5/" class="woocommerce-LoopProduct-link">
                <img src="/wp-content/uploads/gun2.jpg" class="wp-post-image">
                <h2 class="woocommerce-loop-product__title">Glock 17 Gen5</h2>
                <span class="price"><span class="woocommerce-Price-amount">CHF 850.00</span></span>
            </a>
        </li>
        <li class="product type-product">
            <a href="/produkt/remington-870/" class="woocommerce-LoopProduct-link">
                <h2 class="woocommerce-loop-product__title">Remington 870</h2>
                <span class="price">Auf Anfrage</span>
            </a>
        </li>
    </ul>
</body>
</html>
"""

SAMPLE_HTML_NO_LISTINGS = """
<html>
<body>
    <div class="woocommerce-info">
        <p>Keine Produkte gefunden</p>
    </div>
</body>
</html>
"""

SAMPLE_HTML_WITH_PAGINATION = """
<html>
<body>
    <ul class="products">
        <li class="product type-product">
            <a href="/produkt/test-gun/" class="woocommerce-LoopProduct-link">
                <h2 class="woocommerce-loop-product__title">Test Gun</h2>
                <span class="price"><span class="woocommerce-Price-amount">CHF 500.00</span></span>
            </a>
        </li>
    </ul>
    <nav class="woocommerce-pagination">
        <ul class="page-numbers">
            <li><a class="page-numbers" href="/produkt-kategorie/waffen/kurzwaffen-waffen/">1</a></li>
            <li><a class="page-numbers" href="/produkt-kategorie/waffen/kurzwaffen-waffen/page/2/">2</a></li>
            <li><a class="page-numbers next" href="/produkt-kategorie/waffen/kurzwaffen-waffen/page/2/">→</a></li>
        </ul>
    </nav>
</body>
</html>
"""

SAMPLE_HTML_RELATIVE_URLS = """
<html>
<body>
    <ul class="products">
        <li class="product type-product">
            <a href="/produkt/test-item/" class="woocommerce-LoopProduct-link">
                <img src="../uploads/photo.jpg" class="wp-post-image">
                <h2 class="woocommerce-loop-product__title">Test Item</h2>
                <span class="price"><span class="woocommerce-Price-amount">CHF 100.00</span></span>
            </a>
        </li>
    </ul>
</body>
</html>
"""

SAMPLE_HTML_MISSING_PRICE = """
<html>
<body>
    <ul class="products">
        <li class="product type-product">
            <a href="/produkt/sig-p226/" class="woocommerce-LoopProduct-link">
                <img src="/wp-content/uploads/gun1.jpg" class="wp-post-image">
                <h2 class="woocommerce-loop-product__title">SIG P226</h2>
            </a>
        </li>
    </ul>
</body>
</html>
"""

SAMPLE_HTML_MISSING_IMAGE = """
<html>
<body>
    <ul class="products">
        <li class="product type-product">
            <a href="/produkt/sig-p226/" class="woocommerce-LoopProduct-link">
                <h2 class="woocommerce-loop-product__title">SIG P226</h2>
                <span class="price"><span class="woocommerce-Price-amount">CHF 1'200.00</span></span>
            </a>
        </li>
    </ul>
</body>
</html>
"""

SAMPLE_HTML_ALT_STRUCTURE = """
<html>
<body>
    <div class="products">
        <article class="product-item type-product">
            <a href="/produkt/browning-hi-power/">
                <img data-src="/wp-content/uploads/lazy.jpg" class="wp-post-image">
                <h3 class="product-title">Browning Hi-Power</h3>
                <div class="price">CHF 2'500.00</div>
            </a>
        </article>
    </div>
</body>
</html>
"""

SAMPLE_HTML_SALE_PRICE = """
<html>
<body>
    <ul class="products">
        <li class="product type-product">
            <a href="/produkt/glock-19/" class="woocommerce-LoopProduct-link">
                <h2 class="woocommerce-loop-product__title">Glock 19</h2>
                <span class="price">
                    <del><span class="woocommerce-Price-amount">CHF 900.00</span></del>
                    <ins><span class="woocommerce-Price-amount">CHF 750.00</span></ins>
                </span>
            </a>
        </li>
    </ul>
</body>
</html>
"""

SAMPLE_HTML_PLACEHOLDER_IMAGE = """
<html>
<body>
    <ul class="products">
        <li class="product type-product">
            <a href="/produkt/test-gun/" class="woocommerce-LoopProduct-link">
                <img src="/wp-content/uploads/xstore/xstore-placeholder-300x300.png" class="wp-post-image">
                <h2 class="woocommerce-loop-product__title">Test Gun</h2>
                <span class="price"><span class="woocommerce-Price-amount">CHF 500.00</span></span>
            </a>
        </li>
    </ul>
</body>
</html>
"""


class TestScrapeWaffenzimmi:
    """Tests for scrape_waffenzimmi main function."""

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

        with patch("backend.scrapers.waffenzimmi.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.waffenzimmi.delay_between_requests", new_callable=AsyncMock):
                results = await scrape_waffenzimmi()

        # One listing per category, but same HTML so we get 2 listings total
        assert len(results) >= 1
        assert results[0]["title"] == "SIG P226 9mm"
        assert results[0]["price"] == 1200.0
        assert results[0]["source"] == SOURCE_NAME
        assert "/produkt/sig-p226-9mm/" in results[0]["link"]

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

        with patch("backend.scrapers.waffenzimmi.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.waffenzimmi.delay_between_requests", new_callable=AsyncMock):
                results = await scrape_waffenzimmi()

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

        with patch("backend.scrapers.waffenzimmi.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.waffenzimmi.delay_between_requests", new_callable=AsyncMock):
                results = await scrape_waffenzimmi()

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

        with patch("backend.scrapers.waffenzimmi.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.waffenzimmi.delay_between_requests", new_callable=AsyncMock):
                results = await scrape_waffenzimmi()

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

        with patch("backend.scrapers.waffenzimmi.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.waffenzimmi.delay_between_requests", new_callable=AsyncMock):
                results = await scrape_waffenzimmi()

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

        with patch("backend.scrapers.waffenzimmi.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.waffenzimmi.delay_between_requests", new_callable=AsyncMock):
                results = await scrape_waffenzimmi()

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

        with patch("backend.scrapers.waffenzimmi.create_http_client", return_value=mock_client):
            results = await scrape_waffenzimmi()

        assert results == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_connection_error(self):
        """Test that connection errors return empty list (AC: 5)."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.waffenzimmi.create_http_client", return_value=mock_client):
            results = await scrape_waffenzimmi()

        assert results == []

    @pytest.mark.asyncio
    async def test_logs_error_on_failure(self):
        """Test that errors are logged (AC: 5)."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Test error"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.waffenzimmi.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.waffenzimmi.logger") as mock_logger:
                results = await scrape_waffenzimmi()

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

        with patch("backend.scrapers.waffenzimmi.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.waffenzimmi.delay_between_requests", new_callable=AsyncMock):
                results = await scrape_waffenzimmi()

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

        with patch("backend.scrapers.waffenzimmi.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.waffenzimmi.delay_between_requests", new_callable=AsyncMock):
                results = await scrape_waffenzimmi()

        assert results[0]["source"] == "waffenzimmi.ch"

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

        with patch("backend.scrapers.waffenzimmi.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.waffenzimmi.delay_between_requests", new_callable=AsyncMock):
                results = await scrape_waffenzimmi()

        assert len(results) >= 1
        assert results[0]["title"] == "Browning Hi-Power"
        assert results[0]["price"] == 2500.0

    @pytest.mark.asyncio
    async def test_handles_sale_price(self):
        """Test that sale prices are extracted correctly."""
        mock_response = MagicMock()
        mock_response.text = SAMPLE_HTML_SALE_PRICE
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.waffenzimmi.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.waffenzimmi.delay_between_requests", new_callable=AsyncMock):
                results = await scrape_waffenzimmi()

        assert len(results) >= 1
        # Should get the sale price (750) from the ins element
        assert results[0]["price"] == 750.0

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

        with patch("backend.scrapers.waffenzimmi.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.waffenzimmi.delay_between_requests", new_callable=AsyncMock):
                await scrape_waffenzimmi()

        # Should have been called at least once per category
        assert mock_client.get.call_count >= len(CATEGORY_URLS)

    @pytest.mark.asyncio
    async def test_pagination_scrapes_multiple_pages(self):
        """Test that scraper handles pagination correctly across multiple pages."""
        page1_html = """
        <html>
        <body>
            <ul class="products">
                <li class="product type-product">
                    <a href="/produkt/gun-1/" class="woocommerce-LoopProduct-link">
                        <h2 class="woocommerce-loop-product__title">Gun 1</h2>
                        <span class="price"><span class="woocommerce-Price-amount">CHF 100.00</span></span>
                    </a>
                </li>
            </ul>
            <nav class="woocommerce-pagination">
                <a class="page-numbers" href="/produkt-kategorie/waffen/kurzwaffen-waffen/page/2/">2</a>
                <a class="page-numbers next" href="/produkt-kategorie/waffen/kurzwaffen-waffen/page/2/">→</a>
            </nav>
        </body>
        </html>
        """
        page2_html = """
        <html>
        <body>
            <ul class="products">
                <li class="product type-product">
                    <a href="/produkt/gun-2/" class="woocommerce-LoopProduct-link">
                        <h2 class="woocommerce-loop-product__title">Gun 2</h2>
                        <span class="price"><span class="woocommerce-Price-amount">CHF 200.00</span></span>
                    </a>
                </li>
            </ul>
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

        with patch("backend.scrapers.waffenzimmi.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.waffenzimmi.delay_between_requests", new_callable=AsyncMock):
                results = await scrape_waffenzimmi()

        # Should have listings from multiple pages
        titles = [r["title"] for r in results]
        assert "Gun 1" in titles
        assert "Gun 2" in titles

    @pytest.mark.asyncio
    async def test_skips_placeholder_images(self):
        """Test that placeholder images are skipped."""
        mock_response = MagicMock()
        mock_response.text = SAMPLE_HTML_PLACEHOLDER_IMAGE
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.waffenzimmi.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.waffenzimmi.delay_between_requests", new_callable=AsyncMock):
                results = await scrape_waffenzimmi()

        assert len(results) >= 1
        assert results[0]["image_url"] is None  # Placeholder should be skipped


class TestExtractTitle:
    """Tests for _extract_title helper function."""

    def test_extracts_title_from_woocommerce_class(self):
        """Extract title from WooCommerce title class."""
        html = '<li class="product"><h2 class="woocommerce-loop-product__title">Test Gun</h2></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".product")
        assert _extract_title(listing) == "Test Gun"

    def test_extracts_title_from_h2(self):
        """Extract title from h2 element."""
        html = '<li class="product"><h2>Test Gun</h2></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".product")
        assert _extract_title(listing) == "Test Gun"

    def test_extracts_title_from_h3(self):
        """Extract title from h3 element."""
        html = '<li class="product"><h3>Test Gun</h3></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".product")
        assert _extract_title(listing) == "Test Gun"

    def test_extracts_title_from_product_link(self):
        """Extract title from product link when no specific title element."""
        html = '<li class="product"><a href="/produkt/my-gun/">My Gun Title</a></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".product")
        assert _extract_title(listing) == "My Gun Title"

    def test_returns_none_for_empty_listing(self):
        """Return None when listing has no content."""
        html = '<li class="product"></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".product")
        result = _extract_title(listing)
        assert result is None


class TestExtractPrice:
    """Tests for _extract_price helper function."""

    def test_extracts_price_from_woocommerce_class(self):
        """Extract price from WooCommerce price class."""
        html = '<li class="product"><span class="price"><span class="woocommerce-Price-amount">CHF 1\'200.00</span></span></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".product")
        assert _extract_price(listing) == 1200.0

    def test_extracts_price_with_decimals(self):
        """Extract price with decimal value."""
        html = '<li class="product"><span class="price"><span class="woocommerce-Price-amount">CHF 850.50</span></span></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".product")
        assert _extract_price(listing) == 850.5

    def test_extracts_price_with_apostrophe_thousands(self):
        """Extract price using apostrophe as thousands separator."""
        html = '<li class="product"><span class="price">CHF 1\'550.00</span></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".product")
        assert _extract_price(listing) == 1550.0

    def test_returns_none_for_auf_anfrage(self):
        """Return None for 'Auf Anfrage'."""
        html = '<li class="product"><span class="price">Auf Anfrage</span></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".product")
        assert _extract_price(listing) is None

    def test_returns_none_for_missing_price(self):
        """Return None when no price element found."""
        html = '<li class="product"><span>No price</span></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".product")
        assert _extract_price(listing) is None

    def test_extracts_sale_price(self):
        """Extract sale price from ins element."""
        html = '''
        <li class="product">
            <span class="price">
                <del><span class="woocommerce-Price-amount">CHF 900.00</span></del>
                <ins><span class="woocommerce-Price-amount">CHF 750.00</span></ins>
            </span>
        </li>
        '''
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".product")
        assert _extract_price(listing) == 750.0

    def test_extracts_price_from_text_with_chf(self):
        """Extract price from text containing CHF."""
        html = '<li class="product">Some text CHF 500.00 more text</li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".product")
        assert _extract_price(listing) == 500.0


class TestExtractLink:
    """Tests for _extract_link helper function."""

    def test_extracts_link_with_produkt_pattern(self):
        """Extract link matching /produkt/ pattern."""
        html = '<li class="product"><a href="/produkt/sig-p226/">Link</a></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".product")
        link = _extract_link(listing)
        assert link == f"{BASE_URL}/produkt/sig-p226/"

    def test_converts_relative_link_to_absolute(self):
        """Convert relative link to absolute URL."""
        html = '<li class="product"><a href="/produkt/glock-17/">Link</a></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".product")
        link = _extract_link(listing)
        assert link.startswith("https://")

    def test_returns_none_for_missing_link(self):
        """Return None when no link found."""
        html = '<li class="product"><span>No link</span></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".product")
        assert _extract_link(listing) is None

    def test_handles_absolute_url(self):
        """Handle already absolute URLs."""
        html = '<li class="product"><a href="https://www.waffenzimmi.ch/produkt/test/">Link</a></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".product")
        link = _extract_link(listing)
        assert link == "https://www.waffenzimmi.ch/produkt/test/"


class TestExtractImageUrl:
    """Tests for _extract_image_url helper function."""

    def test_extracts_image_from_src(self):
        """Extract image URL from src attribute."""
        html = '<li class="product"><img src="/wp-content/uploads/gun.jpg" class="wp-post-image"></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".product")
        image_url = _extract_image_url(listing)
        assert image_url == f"{BASE_URL}/wp-content/uploads/gun.jpg"

    def test_extracts_image_from_data_src(self):
        """Extract image URL from data-src attribute (lazy loading)."""
        html = '<li class="product"><img data-src="/wp-content/uploads/lazy.jpg" class="wp-post-image"></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".product")
        image_url = _extract_image_url(listing)
        assert image_url == f"{BASE_URL}/wp-content/uploads/lazy.jpg"

    def test_returns_none_for_missing_image(self):
        """Return None when no image found."""
        html = '<li class="product"><span>No image</span></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".product")
        assert _extract_image_url(listing) is None

    def test_skips_placeholder_images(self):
        """Skip images that are placeholders."""
        html = '<li class="product"><img src="/xstore/xstore-placeholder.png" class="wp-post-image"></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".product")
        assert _extract_image_url(listing) is None

    def test_skips_blank_images(self):
        """Skip images that are blank."""
        html = '<li class="product"><img src="/images/blank.gif" class="wp-post-image"></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".product")
        assert _extract_image_url(listing) is None


class TestHasNextPage:
    """Tests for _has_next_page helper function."""

    def test_detects_pagination_with_next_link(self):
        """Detect pagination via next class link."""
        soup = BeautifulSoup(SAMPLE_HTML_WITH_PAGINATION, "lxml")
        assert _has_next_page(soup) is True

    def test_returns_false_for_no_pagination(self):
        """Return False when no pagination found."""
        soup = BeautifulSoup(SAMPLE_HTML_NO_LISTINGS, "lxml")
        assert _has_next_page(soup) is False

    def test_detects_weiter_link(self):
        """Detect pagination via 'Weiter' (Next) link."""
        html = """
        <html><body>
            <nav class="woocommerce-pagination">
                <a href="/page/2/">Weiter</a>
            </nav>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        assert _has_next_page(soup) is True

    def test_detects_page_number_links(self):
        """Detect pagination via page number links."""
        html = """
        <html><body>
            <nav class="woocommerce-pagination">
                <a class="page-numbers" href="/produkt-kategorie/waffen/page/1/">1</a>
                <a class="page-numbers" href="/produkt-kategorie/waffen/page/2/">2</a>
            </nav>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        assert _has_next_page(soup) is True


class TestParseListing:
    """Tests for _parse_listing helper function."""

    def test_parses_complete_listing(self):
        """Parse a listing with all fields."""
        html = """
        <li class="product type-product">
            <a href="/produkt/test-gun/" class="woocommerce-LoopProduct-link">
                <img src="/wp-content/uploads/gun.jpg" class="wp-post-image">
                <h2 class="woocommerce-loop-product__title">Test Gun</h2>
                <span class="price"><span class="woocommerce-Price-amount">CHF 1'000.00</span></span>
            </a>
        </li>
        """
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".product")
        result = _parse_listing(listing)

        assert result is not None
        assert result["title"] == "Test Gun"
        assert result["price"] == 1000.0
        assert "/produkt/test-gun/" in result["link"]
        assert result["image_url"] == f"{BASE_URL}/wp-content/uploads/gun.jpg"
        assert result["source"] == SOURCE_NAME

    def test_returns_none_for_missing_title(self):
        """Return None when title is missing."""
        html = '<li class="product"><a href="/produkt/item/"></a></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".product")
        result = _parse_listing(listing)
        assert result is None

    def test_returns_none_for_missing_link(self):
        """Return None when link is missing."""
        html = '<li class="product"><h2 class="woocommerce-loop-product__title">Test</h2></li>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".product")
        result = _parse_listing(listing)
        assert result is None

    def test_handles_partial_data(self):
        """Handle listing with only required fields (title, link)."""
        html = """
        <li class="product type-product">
            <a href="/produkt/test-gun/" class="woocommerce-LoopProduct-link">
                <h2 class="woocommerce-loop-product__title">Test Gun</h2>
            </a>
        </li>
        """
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one(".product")
        result = _parse_listing(listing)

        assert result is not None
        assert result["title"] == "Test Gun"
        assert "/produkt/test-gun/" in result["link"]
        assert result["price"] is None
        assert result["image_url"] is None
