"""
Tests for sources admin routes (Epic 5).

Tests the sources administration functionality:
- 5.1: Display sources list
- 5.2: Toggle source active state
- 5.3: Display source status
- 5.4: Display source errors
"""
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import SessionLocal, Base, engine
from backend.database.models import Source


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def db_session():
    """Create a fresh database session for each test."""
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)


@pytest.fixture
def sample_sources(db_session):
    """Create sample sources for testing."""
    sources = [
        Source(
            name="waffenboerse.ch",
            base_url="https://www.waffenboerse.ch",
            is_active=True,
            last_crawl_at=datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
            last_error=None,
        ),
        Source(
            name="waffengebraucht.ch",
            base_url="https://www.waffengebraucht.ch",
            is_active=True,
            last_crawl_at=datetime(2024, 1, 15, 10, 35, tzinfo=timezone.utc),
            last_error="Connection timeout after 30s",
        ),
        Source(
            name="waffenzimmi.ch",
            base_url="https://www.waffenzimmi.ch",
            is_active=False,
            last_crawl_at=None,
            last_error=None,
        ),
    ]
    for source in sources:
        db_session.add(source)
    db_session.commit()

    for source in sources:
        db_session.refresh(source)

    return sources


class TestDisplaySourcesList:
    """Tests for Story 5.1: Display Sources List (FR11)."""

    def test_admin_page_returns_200(self, client):
        """Test that admin page returns 200 status."""
        response = client.get("/admin/sources")
        assert response.status_code == 200

    def test_admin_page_is_html(self, client):
        """Test that admin page returns HTML."""
        response = client.get("/admin/sources")
        assert "text/html" in response.headers["content-type"]

    def test_admin_page_has_title(self, client):
        """Test that admin page has correct title."""
        response = client.get("/admin/sources")
        assert "Quellen verwalten" in response.text

    def test_empty_state_shown_when_no_sources(self, client):
        """Test that empty state is shown when no sources exist."""
        response = client.get("/admin/sources")
        assert "Keine Quellen" in response.text

    def test_sources_listed_when_exist(self, client, sample_sources):
        """Test that sources are listed when they exist."""
        response = client.get("/admin/sources")

        assert "waffenboerse.ch" in response.text
        assert "waffengebraucht.ch" in response.text
        assert "waffenzimmi.ch" in response.text

    def test_sources_sorted_alphabetically(self, client, sample_sources):
        """Test that sources are sorted alphabetically."""
        response = client.get("/admin/sources")

        # Extract just the table body
        tbody_start = response.text.find("<tbody")
        tbody_end = response.text.find("</tbody>")
        table_content = response.text[tbody_start:tbody_end]

        # Find positions within the table body
        boerse_pos = table_content.find("waffenboerse.ch")
        gebraucht_pos = table_content.find("waffengebraucht.ch")
        zimmi_pos = table_content.find("waffenzimmi.ch")

        # Should appear in alphabetical order
        assert boerse_pos < gebraucht_pos < zimmi_pos

    def test_source_url_displayed(self, client, sample_sources):
        """Test that source URLs are displayed."""
        response = client.get("/admin/sources")

        assert "https://www.waffenboerse.ch" in response.text
        assert "https://www.waffengebraucht.ch" in response.text


class TestToggleSourceActive:
    """Tests for Story 5.2: Toggle Source Active State (FR12)."""

    def test_toggle_active_to_inactive(self, client, sample_sources, db_session):
        """Test toggling source from active to inactive."""
        source_id = sample_sources[0].id  # waffenboerse.ch is active

        response = client.patch(f"/admin/sources/{source_id}/toggle")

        assert response.status_code == 200
        assert "Inaktiv" in response.text

    def test_toggle_inactive_to_active(self, client, sample_sources, db_session):
        """Test toggling source from inactive to active."""
        source_id = sample_sources[2].id  # waffenzimmi.ch is inactive

        response = client.patch(f"/admin/sources/{source_id}/toggle")

        assert response.status_code == 200
        assert "Aktiv" in response.text

    def test_toggle_persists_to_database(self, client, sample_sources, db_session):
        """Test that toggle persists to database."""
        source_id = sample_sources[0].id  # active

        client.patch(f"/admin/sources/{source_id}/toggle")

        db_session.expire_all()
        source = db_session.query(Source).filter(Source.id == source_id).first()
        assert source.is_active is False

    def test_toggle_twice_returns_to_original(self, client, sample_sources, db_session):
        """Test that toggling twice returns to original value."""
        source_id = sample_sources[0].id  # active

        client.patch(f"/admin/sources/{source_id}/toggle")  # -> inactive
        client.patch(f"/admin/sources/{source_id}/toggle")  # -> active

        db_session.expire_all()
        source = db_session.query(Source).filter(Source.id == source_id).first()
        assert source.is_active is True

    def test_toggle_nonexistent_source(self, client, db_session):
        """Test toggling non-existent source."""
        response = client.patch("/admin/sources/9999/toggle")
        assert response.status_code == 200

    def test_deactivate_button_shown_for_active(self, client, sample_sources):
        """Test that deactivate button is shown for active sources."""
        response = client.get("/admin/sources")
        assert "Deaktivieren" in response.text

    def test_activate_button_shown_for_inactive(self, client, sample_sources):
        """Test that activate button is shown for inactive sources."""
        response = client.get("/admin/sources")
        assert "Aktivieren" in response.text


class TestDisplaySourceStatus:
    """Tests for Story 5.3: Display Source Status (FR13)."""

    def test_active_status_badge_shown(self, client, sample_sources):
        """Test that active status badge is shown."""
        response = client.get("/admin/sources")
        assert "Aktiv" in response.text

    def test_inactive_status_badge_shown(self, client, sample_sources):
        """Test that inactive status badge is shown."""
        response = client.get("/admin/sources")
        assert "Inaktiv" in response.text

    def test_last_crawl_timestamp_shown(self, client, sample_sources):
        """Test that last crawl timestamp is shown."""
        response = client.get("/admin/sources")

        # Should show the date in German format
        assert "15.01.2024" in response.text
        assert "10:30" in response.text

    def test_never_crawled_shows_nie(self, client, sample_sources):
        """Test that 'Nie' is shown when never crawled."""
        response = client.get("/admin/sources")
        assert "Nie" in response.text

    def test_ok_status_shown_for_successful_crawl(self, client, sample_sources):
        """Test that OK status is shown for successful crawl."""
        response = client.get("/admin/sources")
        # waffenboerse.ch has no error and was crawled
        # The OK text may have whitespace around it in the span
        assert "bg-green-100" in response.text and "OK" in response.text


class TestDisplaySourceErrors:
    """Tests for Story 5.4: Display Source Errors (FR14)."""

    def test_error_badge_shown(self, client, sample_sources):
        """Test that error badge is shown when source has error."""
        response = client.get("/admin/sources")
        assert "Fehler" in response.text

    def test_error_message_displayed(self, client, sample_sources):
        """Test that error message is displayed."""
        response = client.get("/admin/sources")
        assert "Connection timeout" in response.text

    def test_clear_error_button_shown(self, client, sample_sources):
        """Test that clear error button is shown for sources with errors."""
        response = client.get("/admin/sources")
        assert "Zurücksetzen" in response.text

    def test_clear_error_removes_error(self, client, sample_sources, db_session):
        """Test that clearing error removes the error message."""
        source_id = sample_sources[1].id  # waffengebraucht.ch has error

        response = client.delete(f"/admin/sources/{source_id}/error")

        assert response.status_code == 200
        # Should no longer show error badge for this row
        assert "Connection timeout" not in response.text

    def test_clear_error_persists_to_database(self, client, sample_sources, db_session):
        """Test that clearing error persists to database."""
        source_id = sample_sources[1].id

        client.delete(f"/admin/sources/{source_id}/error")

        db_session.expire_all()
        source = db_session.query(Source).filter(Source.id == source_id).first()
        assert source.last_error is None

    def test_no_error_section_when_no_errors(self, client, db_session):
        """Test that no error section is shown when source has no errors."""
        # Create a source with no errors
        source = Source(
            name="test.ch",
            base_url="https://test.ch",
            is_active=True,
            last_crawl_at=datetime.now(timezone.utc),
            last_error=None,
        )
        db_session.add(source)
        db_session.commit()

        response = client.get("/admin/sources")

        # Should show OK, not Fehler for this source
        assert "OK" in response.text


class TestCRUDFunctions:
    """Tests for CRUD helper functions."""

    def test_get_all_sources_sorted(self, db_session, sample_sources):
        """Test that get_all_sources_sorted returns alphabetically sorted sources."""
        from backend.database import get_all_sources_sorted

        sources = get_all_sources_sorted(db_session)

        assert len(sources) == 3
        assert sources[0].name == "waffenboerse.ch"
        assert sources[1].name == "waffengebraucht.ch"
        assert sources[2].name == "waffenzimmi.ch"

    def test_get_source_by_id(self, db_session, sample_sources):
        """Test getting source by ID."""
        from backend.database import get_source_by_id

        source = get_source_by_id(db_session, sample_sources[0].id)

        assert source is not None
        assert source.name == "waffenboerse.ch"

    def test_get_source_by_id_not_found(self, db_session):
        """Test getting non-existent source by ID."""
        from backend.database import get_source_by_id

        source = get_source_by_id(db_session, 9999)

        assert source is None

    def test_toggle_source_active(self, db_session, sample_sources):
        """Test toggling source active state."""
        from backend.database import toggle_source_active

        source_id = sample_sources[0].id
        original_state = sample_sources[0].is_active

        toggled = toggle_source_active(db_session, source_id)

        assert toggled is not None
        assert toggled.is_active != original_state

    def test_toggle_source_active_not_found(self, db_session):
        """Test toggling non-existent source."""
        from backend.database import toggle_source_active

        result = toggle_source_active(db_session, 9999)

        assert result is None

    def test_update_source_last_crawl_success(self, db_session, sample_sources):
        """Test updating source last crawl on success."""
        from backend.database import update_source_last_crawl

        source_id = sample_sources[0].id

        updated = update_source_last_crawl(db_session, source_id, error=None)

        assert updated is not None
        assert updated.last_error is None
        assert updated.last_crawl_at is not None

    def test_update_source_last_crawl_with_error(self, db_session, sample_sources):
        """Test updating source last crawl with error."""
        from backend.database import update_source_last_crawl

        source_id = sample_sources[0].id
        error_msg = "Test error message"

        updated = update_source_last_crawl(db_session, source_id, error=error_msg)

        assert updated is not None
        assert updated.last_error == error_msg

    def test_clear_source_error(self, db_session, sample_sources):
        """Test clearing source error."""
        from backend.database import clear_source_error

        source_id = sample_sources[1].id  # has error

        cleared = clear_source_error(db_session, source_id)

        assert cleared is not None
        assert cleared.last_error is None

    def test_clear_source_error_not_found(self, db_session):
        """Test clearing error on non-existent source."""
        from backend.database import clear_source_error

        result = clear_source_error(db_session, 9999)

        assert result is None
