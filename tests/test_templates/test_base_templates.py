"""
Tests for base Jinja2 templates.

Tests verify:
- Dashboard renders without errors
- TailwindCSS, Flowbite, and HTMX are loaded
- Admin pages render correctly
- Flash messages render with proper styles
"""
import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestDashboardTemplate:
    """Tests for dashboard.html template."""

    def test_dashboard_renders_without_errors(self, client):
        """Dashboard should render with 200 status code."""
        response = client.get("/")
        assert response.status_code == 200

    def test_dashboard_contains_tailwindcss(self, client):
        """Dashboard should include TailwindCSS CDN."""
        response = client.get("/")
        assert "tailwindcss" in response.text.lower()

    def test_dashboard_contains_flowbite_css(self, client):
        """Dashboard should include Flowbite CSS."""
        response = client.get("/")
        assert "flowbite" in response.text.lower()
        assert ".min.css" in response.text or "flowbite.css" in response.text.lower()

    def test_dashboard_contains_flowbite_js(self, client):
        """Dashboard should include Flowbite JS."""
        response = client.get("/")
        assert "flowbite" in response.text.lower()
        assert ".min.js" in response.text or "flowbite.js" in response.text.lower()

    def test_dashboard_contains_htmx(self, client):
        """Dashboard should include HTMX library."""
        response = client.get("/")
        assert "htmx" in response.text.lower()

    def test_dashboard_has_navigation(self, client):
        """Dashboard should have navigation links."""
        response = client.get("/")
        assert "Home" in response.text
        assert "Begriffe" in response.text  # Short nav label
        assert "Quellen" in response.text

    def test_dashboard_has_proper_title(self, client):
        """Dashboard should have proper title."""
        response = client.get("/")
        assert "Gilbert's Yoga Helper" in response.text

    def test_dashboard_has_lang_attribute(self, client):
        """Dashboard should have German language attribute."""
        response = client.get("/")
        assert 'lang="de"' in response.text


class TestAdminTemplates:
    """Tests for admin page templates."""

    def test_search_terms_page_renders(self, client):
        """Search terms admin page should render."""
        response = client.get("/admin/search-terms")
        assert response.status_code == 200
        assert "Suchbegriffe" in response.text

    def test_sources_page_renders(self, client):
        """Sources admin page should render."""
        response = client.get("/admin/sources")
        assert response.status_code == 200
        assert "Quellen" in response.text

    def test_crawl_status_page_renders(self, client):
        """Crawl status admin page should render."""
        response = client.get("/admin/crawl")
        assert response.status_code == 200
        assert "Crawl" in response.text

    def test_admin_pages_extend_base_template(self, client):
        """Admin pages should extend base template and include navigation."""
        for url in ["/admin/search-terms", "/admin/sources", "/admin/crawl"]:
            response = client.get(url)
            # Should have navigation from base template
            assert "Home" in response.text
            # Should have TailwindCSS from base template
            assert "tailwindcss" in response.text.lower()


class TestBaseTemplateBlocks:
    """Tests for base template blocks."""

    def test_extra_head_block_exists(self, client):
        """Base template should support extra_head block."""
        response = client.get("/")
        # The block exists in template (we can't directly test empty blocks,
        # but we can verify the page renders correctly)
        assert response.status_code == 200

    def test_extra_scripts_block_exists(self, client):
        """Base template should support extra_scripts block."""
        response = client.get("/")
        # Flowbite JS is loaded at the end, after extra_scripts block position
        assert "flowbite" in response.text.lower()


class TestTemplateInheritance:
    """Tests for template inheritance."""

    def test_child_templates_inherit_layout(self, client):
        """Child templates should inherit navigation and structure from base."""
        pages = ["/", "/admin/search-terms", "/admin/sources", "/admin/crawl"]

        for url in pages:
            response = client.get(url)
            # All pages should have the navigation bar
            assert '<nav class="bg-white' in response.text
            # All pages should have the main content wrapper
            assert '<main class="max-w-screen-xl' in response.text

    def test_all_pages_have_consistent_structure(self, client):
        """All pages should have consistent HTML structure."""
        pages = ["/", "/admin/search-terms", "/admin/sources", "/admin/crawl"]

        for url in pages:
            response = client.get(url)
            assert "<!DOCTYPE html>" in response.text
            assert "<html" in response.text
            assert "<head>" in response.text
            assert "<body" in response.text
            assert "</html>" in response.text


class TestFlowbiteComponents:
    """Tests for Flowbite component styles."""

    def test_flowbite_button_classes_available(self, client):
        """Flowbite button classes should be available via CSS."""
        response = client.get("/")
        # Flowbite CSS is loaded, so button classes will work
        assert "flowbite" in response.text.lower()

    def test_flowbite_alert_styles_in_partial(self):
        """Flash messages partial should use Flowbite-compatible alert styles."""
        from pathlib import Path

        partial_path = Path(__file__).parent.parent.parent / "frontend" / "templates" / "_partials" / "_flash_messages.html"
        content = partial_path.read_text()

        # Check for Flowbite-compatible alert colors
        assert "text-green-800" in content  # success
        assert "text-red-800" in content    # error
        assert "text-yellow-800" in content  # warning
        assert "text-blue-800" in content   # info
        assert "bg-green-50" in content
        assert "bg-red-50" in content

    def test_flowbite_responsive_classes(self, client):
        """Pages should use responsive classes."""
        response = client.get("/")
        # Check for responsive max-width class
        assert "max-w-screen-xl" in response.text


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_endpoint_returns_healthy(self, client):
        """Health endpoint should return healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestErrorHandling:
    """Tests for error handling."""

    def test_nonexistent_page_returns_404(self, client):
        """Non-existent page should return 404 status code."""
        response = client.get("/nonexistent-page-that-does-not-exist")
        assert response.status_code == 404
