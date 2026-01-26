"""
Tests for database CRUD operations.

Tests verify:
- Source management (get, create)
- Search term queries
- Match persistence with deduplication
- Foreign key relationships
- Timestamps
"""
import pytest

from backend.database.crud import (
    create_search_term,
    get_active_search_terms,
    get_active_sources,
    get_all_matches,
    get_all_search_terms,
    get_all_sources,
    get_match_by_url_and_term,
    get_matches_by_search_term,
    get_new_matches,
    get_or_create_source,
    get_source_by_name,
    save_match,
    save_matches,
    search_term_to_dict,
)
from backend.database.models import Match, SearchTerm, Source


class TestSourceOperations:
    """Tests for source CRUD operations."""

    def test_get_source_by_name_returns_none_if_not_found(self, test_session):
        """get_source_by_name returns None if source doesn't exist."""
        result = get_source_by_name(test_session, "nonexistent.ch")
        assert result is None

    def test_get_source_by_name_returns_source_if_exists(self, test_session):
        """get_source_by_name returns source if it exists."""
        # Create a source
        source = Source(name="waffenboerse.ch", base_url="https://waffenboerse.ch")
        test_session.add(source)
        test_session.commit()

        # Query it
        result = get_source_by_name(test_session, "waffenboerse.ch")
        assert result is not None
        assert result.name == "waffenboerse.ch"

    def test_get_or_create_source_creates_new(self, test_session):
        """get_or_create_source creates new source if not exists."""
        result = get_or_create_source(
            test_session,
            name="newsite.ch",
            base_url="https://newsite.ch"
        )

        assert result is not None
        assert result.name == "newsite.ch"
        assert result.base_url == "https://newsite.ch"
        assert result.is_active is True
        assert result.id is not None

    def test_get_or_create_source_returns_existing(self, test_session):
        """get_or_create_source returns existing source if exists."""
        # Create a source first
        source = Source(name="existing.ch", base_url="https://existing.ch")
        test_session.add(source)
        test_session.commit()
        original_id = source.id

        # Call get_or_create
        result = get_or_create_source(
            test_session,
            name="existing.ch",
            base_url="https://different-url.ch"  # Different URL
        )

        # Should return existing, not create new
        assert result.id == original_id
        assert result.base_url == "https://existing.ch"  # Original URL preserved

    def test_get_all_sources(self, test_session):
        """get_all_sources returns all sources."""
        test_session.add(Source(name="source1.ch", base_url="https://source1.ch"))
        test_session.add(Source(name="source2.ch", base_url="https://source2.ch"))
        test_session.commit()

        results = get_all_sources(test_session)
        assert len(results) == 2

    def test_get_active_sources(self, test_session):
        """get_active_sources returns only active sources."""
        test_session.add(Source(name="active.ch", base_url="https://active.ch", is_active=True))
        test_session.add(Source(name="inactive.ch", base_url="https://inactive.ch", is_active=False))
        test_session.commit()

        results = get_active_sources(test_session)
        assert len(results) == 1
        assert results[0].name == "active.ch"


class TestSearchTermOperations:
    """Tests for search term CRUD operations."""

    def test_get_active_search_terms(self, test_session):
        """get_active_search_terms returns only active terms."""
        test_session.add(SearchTerm(term="Glock", is_active=True))
        test_session.add(SearchTerm(term="SIG", is_active=False))
        test_session.commit()

        results = get_active_search_terms(test_session)
        assert len(results) == 1
        assert results[0].term == "Glock"

    def test_get_all_search_terms(self, test_session):
        """get_all_search_terms returns all terms."""
        test_session.add(SearchTerm(term="Glock", is_active=True))
        test_session.add(SearchTerm(term="SIG", is_active=False))
        test_session.commit()

        results = get_all_search_terms(test_session)
        assert len(results) == 2

    def test_search_term_to_dict(self, test_session):
        """search_term_to_dict converts model to dict correctly."""
        term = SearchTerm(term="Glock 17", match_type="exact", is_active=True)
        test_session.add(term)
        test_session.commit()

        result = search_term_to_dict(term)

        assert result["id"] == term.id
        assert result["term"] == "Glock 17"
        assert result["match_type"] == "exact"
        assert result["is_active"] is True

    def test_create_search_term(self, test_session):
        """create_search_term creates and returns new term."""
        term = create_search_term(test_session, "VZ61", match_type="similar")

        assert term.id is not None
        assert term.term == "VZ61"
        assert term.match_type == "similar"
        assert term.is_active is True

    def test_create_search_term_defaults(self, test_session):
        """create_search_term uses correct defaults."""
        term = create_search_term(test_session, "Test")

        assert term.match_type == "exact"
        assert term.is_active is True


class TestMatchOperations:
    """Tests for match CRUD operations."""

    @pytest.fixture
    def setup_source_and_term(self, test_session):
        """Create source and search term for match tests."""
        source = Source(name="test.ch", base_url="https://test.ch")
        term = SearchTerm(term="Glock", match_type="exact")
        test_session.add(source)
        test_session.add(term)
        test_session.commit()
        return source, term

    def test_get_match_by_url_and_term_returns_none_if_not_found(
        self, test_session, setup_source_and_term
    ):
        """get_match_by_url_and_term returns None if not found."""
        source, term = setup_source_and_term

        result = get_match_by_url_and_term(
            test_session,
            url="https://test.ch/listing/123",
            search_term_id=term.id
        )
        assert result is None

    def test_get_match_by_url_and_term_returns_match_if_found(
        self, test_session, setup_source_and_term
    ):
        """get_match_by_url_and_term returns match if exists."""
        source, term = setup_source_and_term

        # Create a match
        match = Match(
            source_id=source.id,
            search_term_id=term.id,
            title="Test Gun",
            url="https://test.ch/listing/123"
        )
        test_session.add(match)
        test_session.commit()

        # Query it
        result = get_match_by_url_and_term(
            test_session,
            url="https://test.ch/listing/123",
            search_term_id=term.id
        )
        assert result is not None
        assert result.title == "Test Gun"

    def test_save_match_creates_new_record(self, test_session, setup_source_and_term):
        """save_match creates new match record (AC: 1)."""
        source, term = setup_source_and_term

        match_result = {
            "listing": {
                "title": "Glock 17 Gen5",
                "price": 650.0,
                "image_url": "https://test.ch/img.jpg",
                "link": "https://test.ch/listing/456",
                "source": "test.ch"
            },
            "search_term_id": term.id,
            "search_term": "Glock",
            "match_type": "exact"
        }

        result = save_match(test_session, match_result, source.id)
        test_session.commit()

        assert result is not None
        assert result.title == "Glock 17 Gen5"
        assert result.price == "650.0"
        assert result.url == "https://test.ch/listing/456"
        assert result.image_url == "https://test.ch/img.jpg"
        assert result.source_id == source.id
        assert result.search_term_id == term.id
        assert result.is_new is True

    def test_save_match_skips_duplicate(self, test_session, setup_source_and_term):
        """save_match returns None for duplicate (same url + term) (AC: 2)."""
        source, term = setup_source_and_term

        match_result = {
            "listing": {
                "title": "Glock 17",
                "price": 600.0,
                "link": "https://test.ch/listing/789",
                "source": "test.ch"
            },
            "search_term_id": term.id,
            "search_term": "Glock",
            "match_type": "exact"
        }

        # Save first time
        result1 = save_match(test_session, match_result, source.id)
        test_session.commit()
        assert result1 is not None

        # Save again - should be duplicate
        result2 = save_match(test_session, match_result, source.id)
        assert result2 is None

    def test_save_match_allows_same_url_different_term(
        self, test_session, setup_source_and_term
    ):
        """Same URL can match different search terms."""
        source, term1 = setup_source_and_term

        # Create second term
        term2 = SearchTerm(term="17", match_type="exact")
        test_session.add(term2)
        test_session.commit()

        listing = {
            "title": "Glock 17",
            "price": 600.0,
            "link": "https://test.ch/listing/same",
            "source": "test.ch"
        }

        # Save with first term
        result1 = save_match(test_session, {
            "listing": listing,
            "search_term_id": term1.id,
            "search_term": "Glock",
            "match_type": "exact"
        }, source.id)
        test_session.commit()

        # Save with second term - should succeed (not duplicate)
        result2 = save_match(test_session, {
            "listing": listing,
            "search_term_id": term2.id,
            "search_term": "17",
            "match_type": "exact"
        }, source.id)
        test_session.commit()

        assert result1 is not None
        assert result2 is not None
        assert result1.id != result2.id

    def test_save_match_handles_null_price(self, test_session, setup_source_and_term):
        """save_match handles None price correctly."""
        source, term = setup_source_and_term

        match_result = {
            "listing": {
                "title": "Rare Item",
                "price": None,  # Auf Anfrage
                "link": "https://test.ch/listing/rare",
                "source": "test.ch"
            },
            "search_term_id": term.id,
            "search_term": "Glock",
            "match_type": "exact"
        }

        result = save_match(test_session, match_result, source.id)
        test_session.commit()

        assert result is not None
        assert result.price is None

    def test_save_match_handles_null_image(self, test_session, setup_source_and_term):
        """save_match handles None image_url correctly."""
        source, term = setup_source_and_term

        match_result = {
            "listing": {
                "title": "No Image Item",
                "price": 500.0,
                "image_url": None,
                "link": "https://test.ch/listing/noimg",
                "source": "test.ch"
            },
            "search_term_id": term.id,
            "search_term": "Glock",
            "match_type": "exact"
        }

        result = save_match(test_session, match_result, source.id)
        test_session.commit()

        assert result is not None
        assert result.image_url is None

    def test_save_match_sets_foreign_keys(self, test_session, setup_source_and_term):
        """save_match correctly sets source_id and search_term_id (AC: 3)."""
        source, term = setup_source_and_term

        match_result = {
            "listing": {
                "title": "FK Test",
                "link": "https://test.ch/listing/fk",
                "source": "test.ch"
            },
            "search_term_id": term.id,
            "search_term": "Glock",
            "match_type": "exact"
        }

        result = save_match(test_session, match_result, source.id)
        test_session.commit()

        # Verify relationships
        assert result.source_id == source.id
        assert result.search_term_id == term.id
        assert result.source.name == "test.ch"
        assert result.search_term.term == "Glock"

    def test_save_match_sets_timestamp(self, test_session, setup_source_and_term):
        """save_match sets created_at timestamp (AC: 4)."""
        source, term = setup_source_and_term

        match_result = {
            "listing": {
                "title": "Timestamp Test",
                "link": "https://test.ch/listing/ts",
                "source": "test.ch"
            },
            "search_term_id": term.id,
            "search_term": "Glock",
            "match_type": "exact"
        }

        result = save_match(test_session, match_result, source.id)
        test_session.commit()

        assert result.created_at is not None
        assert result.updated_at is not None

    def test_save_match_returns_none_for_invalid_input(self, test_session):
        """save_match returns None for invalid input."""
        # Missing url
        result1 = save_match(test_session, {
            "listing": {"title": "Test"},
            "search_term_id": 1
        }, 1)
        assert result1 is None

        # Missing search_term_id
        result2 = save_match(test_session, {
            "listing": {"link": "https://test.ch"}
        }, 1)
        assert result2 is None


class TestBulkSaveMatches:
    """Tests for bulk save_matches function."""

    @pytest.fixture
    def setup_sources_and_terms(self, test_session):
        """Create sources and search terms for bulk tests."""
        source1 = Source(name="source1.ch", base_url="https://source1.ch")
        source2 = Source(name="source2.ch", base_url="https://source2.ch")
        term1 = SearchTerm(term="Glock", match_type="exact")
        term2 = SearchTerm(term="SIG", match_type="similar")

        test_session.add_all([source1, source2, term1, term2])
        test_session.commit()

        source_map = {
            "source1.ch": source1.id,
            "source2.ch": source2.id
        }

        return source_map, term1, term2

    def test_save_matches_bulk(self, test_session, setup_sources_and_terms):
        """save_matches saves multiple matches in bulk."""
        source_map, term1, term2 = setup_sources_and_terms

        match_results = [
            {
                "listing": {
                    "title": "Glock 17",
                    "price": 600.0,
                    "link": "https://source1.ch/1",
                    "source": "source1.ch"
                },
                "search_term_id": term1.id,
                "search_term": "Glock",
                "match_type": "exact"
            },
            {
                "listing": {
                    "title": "SIG 550",
                    "price": 2000.0,
                    "link": "https://source2.ch/1",
                    "source": "source2.ch"
                },
                "search_term_id": term2.id,
                "search_term": "SIG",
                "match_type": "similar"
            },
        ]

        new_count, dup_count = save_matches(test_session, match_results, source_map)

        assert new_count == 2
        assert dup_count == 0

        # Verify in database
        all_matches = get_all_matches(test_session)
        assert len(all_matches) == 2

    def test_save_matches_counts_duplicates(self, test_session, setup_sources_and_terms):
        """save_matches counts duplicates correctly."""
        source_map, term1, term2 = setup_sources_and_terms

        match_results = [
            {
                "listing": {
                    "title": "Glock 17",
                    "link": "https://source1.ch/dup",
                    "source": "source1.ch"
                },
                "search_term_id": term1.id,
                "search_term": "Glock",
                "match_type": "exact"
            },
        ]

        # First save
        new1, dup1 = save_matches(test_session, match_results, source_map)
        assert new1 == 1
        assert dup1 == 0

        # Second save - same data
        new2, dup2 = save_matches(test_session, match_results, source_map)
        assert new2 == 0
        assert dup2 == 1

    def test_save_matches_skips_unknown_source(self, test_session, setup_sources_and_terms):
        """save_matches skips matches with unknown source."""
        source_map, term1, term2 = setup_sources_and_terms

        match_results = [
            {
                "listing": {
                    "title": "Unknown Source",
                    "link": "https://unknown.ch/1",
                    "source": "unknown.ch"  # Not in source_map
                },
                "search_term_id": term1.id,
                "search_term": "Glock",
                "match_type": "exact"
            },
        ]

        new_count, dup_count = save_matches(test_session, match_results, source_map)

        assert new_count == 0
        assert dup_count == 0

    def test_save_matches_empty_list(self, test_session):
        """save_matches handles empty list."""
        new_count, dup_count = save_matches(test_session, [], {})

        assert new_count == 0
        assert dup_count == 0


class TestMatchQueries:
    """Tests for match query functions."""

    @pytest.fixture
    def setup_matches(self, test_session):
        """Create matches for query tests."""
        source = Source(name="test.ch", base_url="https://test.ch")
        term1 = SearchTerm(term="Glock", match_type="exact")
        term2 = SearchTerm(term="SIG", match_type="exact")

        test_session.add_all([source, term1, term2])
        test_session.commit()

        match1 = Match(
            source_id=source.id,
            search_term_id=term1.id,
            title="Glock 17",
            url="https://test.ch/1",
            is_new=True
        )
        match2 = Match(
            source_id=source.id,
            search_term_id=term1.id,
            title="Glock 19",
            url="https://test.ch/2",
            is_new=False
        )
        match3 = Match(
            source_id=source.id,
            search_term_id=term2.id,
            title="SIG 550",
            url="https://test.ch/3",
            is_new=True
        )

        test_session.add_all([match1, match2, match3])
        test_session.commit()

        return source, term1, term2

    def test_get_matches_by_search_term(self, test_session, setup_matches):
        """get_matches_by_search_term returns matches for specific term."""
        source, term1, term2 = setup_matches

        results = get_matches_by_search_term(test_session, term1.id)

        assert len(results) == 2
        titles = {r.title for r in results}
        assert "Glock 17" in titles
        assert "Glock 19" in titles

    def test_get_all_matches(self, test_session, setup_matches):
        """get_all_matches returns all matches."""
        source, term1, term2 = setup_matches

        results = get_all_matches(test_session)

        assert len(results) == 3

    def test_get_new_matches(self, test_session, setup_matches):
        """get_new_matches returns only new matches."""
        source, term1, term2 = setup_matches

        results = get_new_matches(test_session)

        assert len(results) == 2
        for match in results:
            assert match.is_new is True
