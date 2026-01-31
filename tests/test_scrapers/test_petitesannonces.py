"""
Tests for petitesannonces.ch scraper.

Tests verify:
- Listing extraction from search results
- Title, price, image, link extraction
- Pagination detection
- Search with category filter
- Error handling
"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.scrapers.petitesannonces import (
    BASE_URL,
    SOURCE_NAME,
    scrape_petitesannonces,
    _extract_image_url,
    _extract_link,
    _extract_price,
    _extract_title,
    _find_listings,
    _has_next_page,
    _parse_listing,
)
from bs4 import BeautifulSoup


# Sample HTML fixtures
SAMPLE_HTML_SINGLE_LISTING = """
<html>
<body>
    <div class="ele">
        <div class="elf"><a href="/a/12345"><img src="/images/gun.jpg"></a></div>
        <div class="elm"><a href="/a/12345">SIG Sauer P226</a></div>
        <div class="elsp">1'200.-</div>
    </div>
</body>
</html>
"""

SAMPLE_HTML_MULTIPLE_LISTINGS = """
<html>
<body>
    <div class="ele">
        <div class="elf"><a href="/a/12345"><img src="/images/sig.jpg"></a></div>
        <div class="elm"><a href="/a/12345">SIG P226</a></div>
        <div class="elsp">1'200.-</div>
    </div>
    <div class="ele">
        <div class="elf"><a href="/a/12346"><img src="/images/glock.jpg"></a></div>
        <div class="elm"><a href="/a/12346">Glock 17</a></div>
        <div class="elsp">850.-</div>
    </div>
    <div class="box">
        <div class="prmt"><a href="/a/12347">Premium CZ 75</a></div>
    </div>
</body>
</html>
"""

SAMPLE_HTML_NO_LISTINGS = """
<html>
<body>
    <div class="no-results">
        <p>Aucune annonce trouvée</p>
    </div>
</body>
</html>
"""

SAMPLE_HTML_WITH_PAGINATION = """
<html>
<body>
    <div class="ele">
        <div class="elm"><a href="/a/12345">Test Gun</a></div>
    </div>
    <div class="pagination">
        <a href="?q=sig&tid=12&p=1">1</a>
        <a href="?q=sig&tid=12&p=2">2</a>
        <a href="?q=sig&tid=12&p=3">3</a>
    </div>
</body>
</html>
"""


class TestFindListings:
    """Tests for _find_listings helper."""

    def test_finds_normal_listings(self):
        """Test finding normal div.ele listings."""
        soup = BeautifulSoup(SAMPLE_HTML_SINGLE_LISTING, "lxml")
        listings = _find_listings(soup)
        assert len(listings) == 1

    def test_finds_premium_listings(self):
        """Test finding premium div.box listings."""
        soup = BeautifulSoup(SAMPLE_HTML_MULTIPLE_LISTINGS, "lxml")
        listings = _find_listings(soup)
        assert len(listings) == 3  # 2 normal + 1 premium

    def test_returns_empty_for_no_listings(self):
        """Test returning empty list when no listings."""
        soup = BeautifulSoup(SAMPLE_HTML_NO_LISTINGS, "lxml")
        listings = _find_listings(soup)
        assert len(listings) == 0


class TestExtractTitle:
    """Tests for _extract_title helper."""

    def test_extracts_title_from_elm(self):
        """Extract title from div.elm structure."""
        html = '<div class="ele"><div class="elm"><a href="/a/123">Test Gun</a></div></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("div.ele")
        assert _extract_title(listing) == "Test Gun"

    def test_extracts_title_from_prmt(self):
        """Extract title from div.prmt (premium) structure."""
        html = '<div class="box"><div class="prmt"><a href="/a/123">Premium Gun</a></div></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("div.box")
        assert _extract_title(listing) == "Premium Gun"

    def test_returns_none_for_missing_title(self):
        """Return None when no title found."""
        html = '<div class="ele"><span>no title</span></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("div.ele")
        assert _extract_title(listing) is None


class TestExtractPrice:
    """Tests for _extract_price helper."""

    def test_extracts_price_from_elsp(self):
        """Extract price from div.elsp element."""
        html = '<div class="ele"><div class="elsp">1\'200.-</div></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("div.ele")
        assert _extract_price(listing) == 1200.0

    def test_extracts_price_with_chf_pattern(self):
        """Extract price from CHF pattern."""
        html = '<div class="ele"><span>CHF 850.00</span></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("div.ele")
        assert _extract_price(listing) == 850.0

    def test_returns_none_for_missing_price(self):
        """Return None when no price found."""
        html = '<div class="ele"><span>No price</span></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("div.ele")
        assert _extract_price(listing) is None


class TestExtractLink:
    """Tests for _extract_link helper."""

    def test_extracts_link(self):
        """Extract link from a[href^='/a/'] element."""
        html = '<div class="ele"><a href="/a/12345">Gun</a></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("div.ele")
        assert _extract_link(listing) == f"{BASE_URL}/a/12345"

    def test_returns_none_for_missing_link(self):
        """Return None when no link found."""
        html = '<div class="ele"><span>No link</span></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("div.ele")
        assert _extract_link(listing) is None


class TestExtractImageUrl:
    """Tests for _extract_image_url helper."""

    def test_extracts_image_from_elf(self):
        """Extract image from div.elf structure."""
        html = '<div class="ele"><div class="elf"><img src="/images/gun.jpg"></div></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("div.ele")
        assert _extract_image_url(listing) == f"{BASE_URL}/images/gun.jpg"

    def test_returns_none_for_missing_image(self):
        """Return None when no image found."""
        html = '<div class="ele"><span>No image</span></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("div.ele")
        assert _extract_image_url(listing) is None


class TestHasNextPage:
    """Tests for _has_next_page helper."""

    def test_detects_pagination(self):
        """Detect pagination links."""
        soup = BeautifulSoup(SAMPLE_HTML_WITH_PAGINATION, "lxml")
        assert _has_next_page(soup, 1) is True

    def test_returns_false_for_last_page(self):
        """Return False when on last page."""
        soup = BeautifulSoup(SAMPLE_HTML_WITH_PAGINATION, "lxml")
        assert _has_next_page(soup, 3) is False

    def test_returns_false_for_no_pagination(self):
        """Return False when no pagination."""
        soup = BeautifulSoup(SAMPLE_HTML_NO_LISTINGS, "lxml")
        assert _has_next_page(soup, 1) is False


class TestParseListing:
    """Tests for _parse_listing helper."""

    def test_parses_complete_listing(self):
        """Parse listing with all fields."""
        html = """
        <div class="ele">
            <div class="elf"><a href="/a/123"><img src="/images/gun.jpg"></a></div>
            <div class="elm"><a href="/a/123">Test Gun</a></div>
            <div class="elsp">1'000.-</div>
        </div>
        """
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("div.ele")
        result = _parse_listing(listing)

        assert result is not None
        assert result["title"] == "Test Gun"
        assert result["price"] == 1000.0
        assert result["source"] == SOURCE_NAME

    def test_returns_none_for_missing_title(self):
        """Return None when title missing."""
        html = '<div class="ele"><a href="/a/123"></a></div>'
        soup = BeautifulSoup(html, "lxml")
        listing = soup.select_one("div.ele")
        assert _parse_listing(listing) is None


class TestScrapePetitesannonces:
    """Tests for scrape_petitesannonces main function."""

    @pytest.mark.asyncio
    async def test_extracts_listings(self):
        """Test listing extraction from search results."""
        mock_response = MagicMock()
        mock_response.text = SAMPLE_HTML_MULTIPLE_LISTINGS
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.scrapers.petitesannonces.create_http_client", return_value=mock_client):
            with patch("backend.scrapers.petitesannonces.delay_between_requests", new_callable=AsyncMock):
                with patch("backend.services.crawler.add_crawl_log"):
                    results = await scrape_petitesannonces(search_terms=["sig"])

        assert len(results) >= 2

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

        with patch("backend.scrapers.petitesannonces.create_http_client", return_value=mock_client):
            with patch("backend.services.crawler.add_crawl_log"):
                results = await scrape_petitesannonces(search_terms=["sig"])

        assert results == []

    @pytest.mark.asyncio
    async def test_returns_empty_for_empty_search_terms(self):
        """Test that empty search terms return empty list."""
        results = await scrape_petitesannonces(search_terms=[])
        assert results == []
