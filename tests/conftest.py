"""
Pytest configuration and fixtures for Gebrauchtwaffen Aggregator tests.
"""
import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI application."""
    with TestClient(app) as test_client:
        yield test_client
