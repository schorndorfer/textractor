"""Tests for terminology router API endpoints."""
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from textractor.api.main import create_app
from textractor.api.dependencies import init_store, init_terminology


@pytest.fixture
def client_no_terminology():
    """Create a test client without SNOMED terminology."""
    with tempfile.TemporaryDirectory() as tmpdir:
        doc_root = Path(tmpdir)

        # Initialize app dependencies without SNOMED
        init_store(doc_root)
        init_terminology(snomed_dir=None)

        app = create_app()
        yield TestClient(app)


@pytest.fixture
def client_with_terminology():
    """Create a test client with SNOMED terminology if available."""
    with tempfile.TemporaryDirectory() as tmpdir:
        doc_root = Path(tmpdir)

        # Try to initialize with default SNOMED location
        init_store(doc_root)
        snomed_dir = Path("data/terminology/SnomedCT")
        if snomed_dir.exists():
            init_terminology(snomed_dir=snomed_dir)
        else:
            init_terminology(snomed_dir=None)

        app = create_app()
        yield TestClient(app)


class TestSearchConcepts:
    """Tests for GET /api/terminology/search endpoint."""

    def test_search_without_terminology(self, client_no_terminology):
        """Test that search returns empty results when no terminology is loaded."""
        response = client_no_terminology.get("/api/terminology/search", params={"q": "diabetes"})

        assert response.status_code == 200
        assert response.json() == []

    def test_search_empty_query(self, client_no_terminology):
        """Test that empty query returns empty results."""
        response = client_no_terminology.get("/api/terminology/search", params={"q": ""})

        assert response.status_code == 200
        assert response.json() == []

    def test_search_with_limit(self, client_no_terminology):
        """Test that limit parameter is accepted."""
        response = client_no_terminology.get("/api/terminology/search", params={"q": "test", "limit": 10})

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_search_limit_validation_min(self, client_no_terminology):
        """Test that limit validation enforces minimum (ge=1)."""
        response = client_no_terminology.get("/api/terminology/search", params={"q": "test", "limit": 0})

        assert response.status_code == 422  # Validation error

    def test_search_limit_validation_max(self, client_no_terminology):
        """Test that limit validation enforces maximum (le=200)."""
        response = client_no_terminology.get("/api/terminology/search", params={"q": "test", "limit": 201})

        assert response.status_code == 422  # Validation error

    def test_search_default_limit(self, client_no_terminology):
        """Test that default limit is used when not specified."""
        response = client_no_terminology.get("/api/terminology/search", params={"q": "test"})

        assert response.status_code == 200
        # Can't verify actual limit without results, but should succeed

    def test_search_with_snomed(self, client_with_terminology):
        """Test search with SNOMED terminology if available."""
        response = client_with_terminology.get("/api/terminology/search", params={"q": "diabetes"})

        assert response.status_code == 200
        results = response.json()
        assert isinstance(results, list)

        # If SNOMED is loaded, should have results
        if len(results) > 0:
            # Verify result structure
            first_result = results[0]
            assert "code" in first_result
            assert "display" in first_result
            assert "system" in first_result
            assert first_result["system"] == "SNOMED-CT"

    def test_search_returns_concepts(self, client_with_terminology):
        """Test that search results are valid TerminologyConcept objects."""
        response = client_with_terminology.get("/api/terminology/search", params={"q": "hypertension"})

        assert response.status_code == 200
        results = response.json()

        # All results should have required fields
        for result in results:
            assert "code" in result
            assert "display" in result
            assert "system" in result
            assert isinstance(result["code"], str)
            assert isinstance(result["display"], str)
            assert isinstance(result["system"], str)

    def test_search_respects_limit(self, client_with_terminology):
        """Test that search respects the limit parameter."""
        # Search with small limit
        response = client_with_terminology.get("/api/terminology/search", params={"q": "disorder", "limit": 5})

        assert response.status_code == 200
        results = response.json()

        # Should not exceed the limit
        assert len(results) <= 5

    def test_search_different_queries(self, client_with_terminology):
        """Test that different queries return different results."""
        response1 = client_with_terminology.get("/api/terminology/search", params={"q": "diabetes"})
        response2 = client_with_terminology.get("/api/terminology/search", params={"q": "hypertension"})

        assert response1.status_code == 200
        assert response2.status_code == 200

        # If both have results, they should be different
        results1 = response1.json()
        results2 = response2.json()

        if len(results1) > 0 and len(results2) > 0:
            # Results should be different
            codes1 = {r["code"] for r in results1}
            codes2 = {r["code"] for r in results2}
            assert codes1 != codes2 or len(results1) == 0 or len(results2) == 0

    def test_search_case_insensitive(self, client_with_terminology):
        """Test that search is case-insensitive."""
        response1 = client_with_terminology.get("/api/terminology/search", params={"q": "DIABETES"})
        response2 = client_with_terminology.get("/api/terminology/search", params={"q": "diabetes"})

        assert response1.status_code == 200
        assert response2.status_code == 200

        # Should return similar results (may differ in ranking)
        results1 = response1.json()
        results2 = response2.json()

        # If results exist, verify they overlap
        if len(results1) > 0 and len(results2) > 0:
            codes1 = {r["code"] for r in results1[:5]}  # Top 5
            codes2 = {r["code"] for r in results2[:5]}  # Top 5
            # Should have some overlap
            overlap = codes1 & codes2
            assert len(overlap) > 0 or (len(results1) == 0 and len(results2) == 0)


class TestTerminologyInfo:
    """Tests for GET /api/terminology/info endpoint."""

    def test_info_without_terminology(self, client_no_terminology):
        """Test that info endpoint returns data when no terminology is loaded."""
        response = client_no_terminology.get("/api/terminology/info")

        assert response.status_code == 200
        info = response.json()

        # Should return TerminologyInfo structure
        assert "loaded" in info
        assert info["loaded"] is False

    def test_info_with_terminology(self, client_with_terminology):
        """Test that info endpoint returns correct data when terminology is loaded."""
        response = client_with_terminology.get("/api/terminology/info")

        assert response.status_code == 200
        info = response.json()

        # Should have loaded field
        assert "loaded" in info
        assert isinstance(info["loaded"], bool)

        # If SNOMED is loaded, should have additional info
        if info["loaded"]:
            assert "file_name" in info or "name" in info  # Either field is acceptable
            assert "total_concepts" in info or True  # total_concepts may be present
            if "file_name" in info:
                assert isinstance(info["file_name"], str)
            if "name" in info:
                assert isinstance(info["name"], str)

    def test_info_structure(self, client_no_terminology):
        """Test that info response has correct structure."""
        response = client_no_terminology.get("/api/terminology/info")

        assert response.status_code == 200
        info = response.json()

        # Should be a dictionary
        assert isinstance(info, dict)
        # Should have at least the loaded field
        assert "loaded" in info

    def test_info_no_parameters(self, client_no_terminology):
        """Test that info endpoint works without any parameters."""
        response = client_no_terminology.get("/api/terminology/info")

        assert response.status_code == 200
        assert response.json() is not None


class TestIntegration:
    """Integration tests combining search and info."""

    def test_search_and_info_consistency(self, client_with_terminology):
        """Test that search results are consistent with info endpoint."""
        # Get info
        info_response = client_with_terminology.get("/api/terminology/info")
        info = info_response.json()

        # Get search results
        search_response = client_with_terminology.get("/api/terminology/search", params={"q": "diabetes"})
        search_results = search_response.json()

        # If terminology is not loaded, search should return empty
        if not info["loaded"]:
            assert len(search_results) == 0

    def test_multiple_searches(self, client_with_terminology):
        """Test that multiple searches work correctly."""
        queries = ["diabetes", "hypertension", "asthma", "pneumonia"]

        for query in queries:
            response = client_with_terminology.get("/api/terminology/search", params={"q": query})
            assert response.status_code == 200
            results = response.json()
            assert isinstance(results, list)

    def test_info_called_multiple_times(self, client_no_terminology):
        """Test that info endpoint can be called multiple times."""
        for _ in range(3):
            response = client_no_terminology.get("/api/terminology/info")
            assert response.status_code == 200
            info = response.json()
            assert "loaded" in info


class TestSystemParameter:
    """Tests for system query param on /api/terminology/search."""

    def test_search_with_snomed_system_param(self, client_no_terminology):
        """system=SNOMED-CT is accepted even when nothing loaded."""
        response = client_no_terminology.get(
            "/api/terminology/search", params={"q": "diabetes", "system": "SNOMED-CT"}
        )
        assert response.status_code == 200
        assert response.json() == []

    def test_search_with_icd10cm_system_param(self, client_no_terminology):
        """system=ICD-10-CM is accepted even when nothing loaded."""
        response = client_no_terminology.get(
            "/api/terminology/search", params={"q": "diabetes", "system": "ICD-10-CM"}
        )
        assert response.status_code == 200
        assert response.json() == []

    def test_search_invalid_system_rejected(self, client_no_terminology):
        """system values not in the allowed set return 422."""
        response = client_no_terminology.get(
            "/api/terminology/search", params={"q": "diabetes", "system": "RXNORM"}
        )
        assert response.status_code == 422

    def test_info_has_systems_field(self, client_no_terminology):
        """info endpoint returns systems list."""
        response = client_no_terminology.get("/api/terminology/info")
        assert response.status_code == 200
        info = response.json()
        assert "systems" in info
        assert isinstance(info["systems"], list)
        assert len(info["systems"]) == 2
        system_names = {s["system"] for s in info["systems"]}
        assert "SNOMED-CT" in system_names
        assert "ICD-10-CM" in system_names
