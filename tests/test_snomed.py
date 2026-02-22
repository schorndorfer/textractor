"""Tests for SNOMED CT search functionality."""
import pytest
import tempfile
from pathlib import Path
from textractor.terminology.snomed import SNOMEDSearch


@pytest.fixture(scope="session")
def snomed_data_dir():
    """Path to SNOMED CT data directory."""
    return Path(__file__).parent.parent / "data" / "terminology" / "SnomedCT"


@pytest.fixture(scope="session")
def snomed_search(snomed_data_dir):
    """Create SNOMED search index with temporary database."""
    if not snomed_data_dir.exists():
        pytest.skip(f"SNOMED data not found at {snomed_data_dir}")

    # Use temporary file for test database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    search = SNOMEDSearch(db_path)
    search.build_index(snomed_data_dir)

    yield search

    # Cleanup
    search.close()
    if db_path.exists():
        db_path.unlink()


def test_snomed_build_index(snomed_search):
    """Test that SNOMED index builds successfully."""
    assert snomed_search.is_indexed()


def test_snomed_search_myocardial_infarction(snomed_search):
    """Test search for 'myocardial infarction'."""
    results = snomed_search.search("myocardial infarction", limit=10)

    assert len(results) > 0
    assert len(results) <= 10

    # Check result structure
    first_result = results[0]
    assert "concept_id" in first_result
    assert "term" in first_result
    assert "type" in first_result
    assert "score" in first_result

    # Search should find relevant results
    result_terms_lower = [r["term"].lower() for r in results]
    assert any("myocardial infarction" in term for term in result_terms_lower)


def test_snomed_search_diabetes(snomed_search):
    """Test search for 'diabetes'."""
    results = snomed_search.search("diabetes", limit=20)

    assert len(results) > 0
    assert len(results) <= 20

    # Should find diabetes-related terms
    result_terms_lower = [r["term"].lower() for r in results]
    assert any("diabetes" in term for term in result_terms_lower)


def test_snomed_search_hypertensive(snomed_search):
    """Test search for 'hypertensive' with custom ranking."""
    results = snomed_search.search("hypertensive", limit=10)

    assert len(results) > 0

    # Terms starting with "hypertensive" should rank highly
    top_terms = [r["term"].lower() for r in results[:3]]
    assert any(term.startswith("hypertensive") for term in top_terms)


def test_snomed_search_empty_query(snomed_search):
    """Test search with empty query."""
    results = snomed_search.search("", limit=10)

    # Empty query should return empty results
    assert len(results) == 0


def test_snomed_search_limit(snomed_search):
    """Test that limit parameter works correctly."""
    results_5 = snomed_search.search("pain", limit=5)
    results_15 = snomed_search.search("pain", limit=15)

    assert len(results_5) <= 5
    assert len(results_15) <= 15
    assert len(results_15) >= len(results_5)


def test_snomed_concept_id_type(snomed_search):
    """Test that concept IDs are integers."""
    results = snomed_search.search("fever", limit=5)

    if len(results) > 0:
        for result in results:
            assert isinstance(result["concept_id"], int)
            assert result["concept_id"] > 0


def test_snomed_persistence():
    """Test that database persists data."""
    snomed_dir = Path(__file__).parent.parent / "data" / "terminology" / "SnomedCT"

    if not snomed_dir.exists():
        pytest.skip(f"SNOMED data not found at {snomed_dir}")

    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    try:
        # Build index
        search1 = SNOMEDSearch(db_path)
        count = search1.build_index(snomed_dir)
        search1.close()

        assert count > 0

        # Re-open database and verify data persists
        search2 = SNOMEDSearch(db_path)
        assert search2.is_indexed()

        results = search2.search("diabetes", limit=5)
        assert len(results) > 0

        search2.close()

    finally:
        # Cleanup
        if db_path.exists():
            db_path.unlink()
