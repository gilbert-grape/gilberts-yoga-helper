"""
Tests for search terms admin routes (Epic 4).

Tests the search terms administration functionality:
- 4.1: Display search terms list
- 4.2: Add new search term
- 4.3: Delete search term
- 4.4: Toggle matching type
"""
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import SessionLocal, Base, engine
from backend.database.models import SearchTerm


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
def sample_terms(db_session):
    """Create sample search terms for testing."""
    terms = [
        SearchTerm(term="Glock 17", match_type="exact", is_active=True),
        SearchTerm(term="SIG 550", match_type="similar", is_active=True),
        SearchTerm(term="Beretta 92", match_type="exact", is_active=True),
    ]
    for term in terms:
        db_session.add(term)
    db_session.commit()

    # Refresh to get IDs
    for term in terms:
        db_session.refresh(term)

    return terms


class TestDisplaySearchTermsList:
    """Tests for Story 4.1: Display Search Terms List (FR10)."""

    def test_admin_page_returns_200(self, client):
        """Test that admin page returns 200 status."""
        response = client.get("/admin/search-terms")
        assert response.status_code == 200

    def test_admin_page_is_html(self, client):
        """Test that admin page returns HTML."""
        response = client.get("/admin/search-terms")
        assert "text/html" in response.headers["content-type"]

    def test_admin_page_has_title(self, client):
        """Test that admin page has correct title."""
        response = client.get("/admin/search-terms")
        assert "Suchbegriffe verwalten" in response.text

    def test_empty_state_shown_when_no_terms(self, client):
        """Test that empty state is shown when no search terms exist."""
        response = client.get("/admin/search-terms")
        assert "Keine Suchbegriffe" in response.text

    def test_terms_listed_when_exist(self, client, sample_terms):
        """Test that search terms are listed when they exist."""
        response = client.get("/admin/search-terms")

        assert "Glock 17" in response.text
        assert "SIG 550" in response.text
        assert "Beretta 92" in response.text

    def test_terms_sorted_alphabetically(self, client, sample_terms):
        """Test that search terms are sorted alphabetically."""
        response = client.get("/admin/search-terms")

        # Extract just the table body section to avoid placeholder text in form
        tbody_start = response.text.find("<tbody")
        tbody_end = response.text.find("</tbody>")
        table_content = response.text[tbody_start:tbody_end]

        # Find positions within the table body
        beretta_pos = table_content.find("Beretta 92")
        glock_pos = table_content.find("Glock 17")
        sig_pos = table_content.find("SIG 550")

        # Should appear in alphabetical order: Beretta < Glock < SIG
        assert beretta_pos < glock_pos < sig_pos

    def test_match_type_shown_for_each_term(self, client, sample_terms):
        """Test that match type (exact/similar) is shown for each term."""
        response = client.get("/admin/search-terms")

        # Should show both match types
        assert "Exakt" in response.text
        assert "Ähnlich" in response.text

    def test_add_form_present(self, client):
        """Test that add search term form is present."""
        response = client.get("/admin/search-terms")
        assert "Neuen Suchbegriff hinzufügen" in response.text
        assert 'name="term"' in response.text


class TestAddSearchTerm:
    """Tests for Story 4.2: Add New Search Term (FR7)."""

    def test_add_term_success(self, client, db_session):
        """Test successfully adding a new search term."""
        response = client.post(
            "/admin/search-terms",
            data={"term": "CZ 75", "match_type": "exact"}
        )

        assert response.status_code == 200
        assert "CZ 75" in response.text
        assert "hinzugefügt" in response.text

    def test_add_term_appears_in_list(self, client, db_session):
        """Test that added term appears in the list."""
        client.post(
            "/admin/search-terms",
            data={"term": "Walther PPK", "match_type": "similar"}
        )

        response = client.get("/admin/search-terms")
        assert "Walther PPK" in response.text

    def test_add_term_with_similar_match_type(self, client, db_session):
        """Test adding a term with similar match type."""
        client.post(
            "/admin/search-terms",
            data={"term": "HK MP5", "match_type": "similar"}
        )

        response = client.get("/admin/search-terms")
        assert "HK MP5" in response.text

    def test_add_empty_term_fails(self, client, db_session):
        """Test that adding empty term shows validation error."""
        response = client.post(
            "/admin/search-terms",
            data={"term": "", "match_type": "exact"}
        )

        assert response.status_code == 200
        assert "darf nicht leer sein" in response.text

    def test_add_whitespace_term_fails(self, client, db_session):
        """Test that adding whitespace-only term shows validation error."""
        response = client.post(
            "/admin/search-terms",
            data={"term": "   ", "match_type": "exact"}
        )

        assert response.status_code == 200
        assert "darf nicht leer sein" in response.text

    def test_add_duplicate_term_fails(self, client, sample_terms):
        """Test that adding duplicate term shows validation error."""
        response = client.post(
            "/admin/search-terms",
            data={"term": "Glock 17", "match_type": "exact"}
        )

        assert response.status_code == 200
        assert "existiert bereits" in response.text

    def test_add_duplicate_case_insensitive(self, client, sample_terms):
        """Test that duplicate check is case-insensitive."""
        response = client.post(
            "/admin/search-terms",
            data={"term": "glock 17", "match_type": "exact"}
        )

        assert response.status_code == 200
        assert "existiert bereits" in response.text


class TestDeleteSearchTerm:
    """Tests for Story 4.3: Delete Search Term (FR8)."""

    def test_delete_term_success(self, client, sample_terms, db_session):
        """Test successfully deleting a search term."""
        term_id = sample_terms[0].id

        response = client.delete(f"/admin/search-terms/{term_id}")

        assert response.status_code == 200
        assert "gelöscht" in response.text

    def test_deleted_term_removed_from_list(self, client, sample_terms, db_session):
        """Test that deleted term is removed from the list."""
        term_id = sample_terms[0].id  # Glock 17

        client.delete(f"/admin/search-terms/{term_id}")

        response = client.get("/admin/search-terms")

        # Extract just the table body to avoid placeholder text in form
        tbody_start = response.text.find("<tbody")
        tbody_end = response.text.find("</tbody>")
        table_content = response.text[tbody_start:tbody_end] if tbody_start != -1 else ""

        assert "Glock 17" not in table_content
        # Other terms should still be there in the table
        assert "SIG 550" in table_content
        assert "Beretta 92" in table_content

    def test_delete_nonexistent_term(self, client, db_session):
        """Test deleting a non-existent term."""
        response = client.delete("/admin/search-terms/9999")

        # Should still return 200 (no error page)
        assert response.status_code == 200

    def test_delete_all_terms_shows_empty_state(self, client, db_session):
        """Test that deleting all terms shows empty state."""
        # Add one term
        client.post(
            "/admin/search-terms",
            data={"term": "Test", "match_type": "exact"}
        )

        # Get the term ID
        response = client.get("/admin/search-terms")
        assert "Test" in response.text

        # Find and delete it (term ID should be 1)
        from backend.database import get_all_search_terms_sorted
        session = SessionLocal()
        terms = get_all_search_terms_sorted(session)
        if terms:
            client.delete(f"/admin/search-terms/{terms[0].id}")
        session.close()

        response = client.get("/admin/search-terms")
        assert "Keine Suchbegriffe" in response.text


class TestToggleMatchType:
    """Tests for Story 4.4: Toggle Matching Type (FR9)."""

    def test_toggle_exact_to_similar(self, client, sample_terms, db_session):
        """Test toggling match type from exact to similar."""
        # Glock 17 is exact
        term_id = sample_terms[0].id

        response = client.patch(f"/admin/search-terms/{term_id}/match-type")

        assert response.status_code == 200
        # Response should show updated row with "Ähnlich"
        assert "Ähnlich" in response.text

    def test_toggle_similar_to_exact(self, client, sample_terms, db_session):
        """Test toggling match type from similar to exact."""
        # SIG 550 is similar
        term_id = sample_terms[1].id

        response = client.patch(f"/admin/search-terms/{term_id}/match-type")

        assert response.status_code == 200
        # Response should show updated row with "Exakt"
        assert "Exakt" in response.text

    def test_toggle_persists_to_database(self, client, sample_terms, db_session):
        """Test that toggle persists to database."""
        term_id = sample_terms[0].id  # Glock 17 - exact

        client.patch(f"/admin/search-terms/{term_id}/match-type")

        # Refresh session to get updated data
        db_session.expire_all()
        term = db_session.query(SearchTerm).filter(SearchTerm.id == term_id).first()
        assert term.match_type == "similar"

    def test_toggle_twice_returns_to_original(self, client, sample_terms, db_session):
        """Test that toggling twice returns to original value."""
        term_id = sample_terms[0].id  # Glock 17 - exact

        # Toggle once (exact -> similar)
        client.patch(f"/admin/search-terms/{term_id}/match-type")
        # Toggle again (similar -> exact)
        client.patch(f"/admin/search-terms/{term_id}/match-type")

        db_session.expire_all()
        term = db_session.query(SearchTerm).filter(SearchTerm.id == term_id).first()
        assert term.match_type == "exact"

    def test_toggle_nonexistent_term(self, client, db_session):
        """Test toggling non-existent term."""
        response = client.patch("/admin/search-terms/9999/match-type")

        # Should return 200 with error message
        assert response.status_code == 200

    def test_toggle_updates_display_immediately(self, client, sample_terms, db_session):
        """Test that toggle updates the display immediately."""
        term_id = sample_terms[0].id

        # Toggle and check response contains updated badge
        response = client.patch(f"/admin/search-terms/{term_id}/match-type")

        # Should contain the new badge in the HTMX response
        assert f'id="term-row-{term_id}"' in response.text


class TestCRUDFunctions:
    """Tests for CRUD helper functions."""

    def test_get_all_search_terms_sorted(self, db_session, sample_terms):
        """Test that get_all_search_terms_sorted returns alphabetically sorted terms."""
        from backend.database import get_all_search_terms_sorted

        terms = get_all_search_terms_sorted(db_session)

        assert len(terms) == 3
        assert terms[0].term == "Beretta 92"
        assert terms[1].term == "Glock 17"
        assert terms[2].term == "SIG 550"

    def test_get_search_term_by_id(self, db_session, sample_terms):
        """Test getting search term by ID."""
        from backend.database import get_search_term_by_id

        term = get_search_term_by_id(db_session, sample_terms[0].id)

        assert term is not None
        assert term.term == "Glock 17"

    def test_get_search_term_by_id_not_found(self, db_session):
        """Test getting non-existent search term by ID."""
        from backend.database import get_search_term_by_id

        term = get_search_term_by_id(db_session, 9999)

        assert term is None

    def test_get_search_term_by_term(self, db_session, sample_terms):
        """Test getting search term by term text."""
        from backend.database import get_search_term_by_term

        term = get_search_term_by_term(db_session, "Glock 17")

        assert term is not None
        assert term.id == sample_terms[0].id

    def test_get_search_term_by_term_case_insensitive(self, db_session, sample_terms):
        """Test that get_search_term_by_term is case-insensitive."""
        from backend.database import get_search_term_by_term

        term = get_search_term_by_term(db_session, "glock 17")

        assert term is not None
        assert term.term == "Glock 17"

    def test_delete_search_term(self, db_session, sample_terms):
        """Test deleting a search term."""
        from backend.database import delete_search_term, get_search_term_by_id

        term_id = sample_terms[0].id
        result = delete_search_term(db_session, term_id)

        assert result is True
        assert get_search_term_by_id(db_session, term_id) is None

    def test_delete_search_term_not_found(self, db_session):
        """Test deleting non-existent search term."""
        from backend.database import delete_search_term

        result = delete_search_term(db_session, 9999)

        assert result is False

    def test_update_search_term_match_type(self, db_session, sample_terms):
        """Test updating search term match type."""
        from backend.database import update_search_term_match_type

        term_id = sample_terms[0].id  # exact
        updated = update_search_term_match_type(db_session, term_id, "similar")

        assert updated is not None
        assert updated.match_type == "similar"

    def test_update_search_term_match_type_invalid(self, db_session, sample_terms):
        """Test updating with invalid match type raises error."""
        from backend.database import update_search_term_match_type

        term_id = sample_terms[0].id

        with pytest.raises(ValueError):
            update_search_term_match_type(db_session, term_id, "invalid")

    def test_update_search_term_match_type_not_found(self, db_session):
        """Test updating non-existent term returns None."""
        from backend.database import update_search_term_match_type

        result = update_search_term_match_type(db_session, 9999, "similar")

        assert result is None
