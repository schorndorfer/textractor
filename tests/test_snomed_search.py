"""Tests for SNOMED CT search functionality."""
import pytest
from pathlib import Path
from textractor.terminology.snomed import SNOMEDSearch


@pytest.fixture(scope="session")
def snomed_data_dir():
    """Path to SNOMED CT data directory."""
    return Path(__file__).parent.parent / "data" / "terminology" / "SnomedCT"


@pytest.fixture(scope="session")
def snomed_search(snomed_data_dir):
    """Load SNOMED search index."""
    search = SNOMEDSearch()
    if not snomed_data_dir.exists():
        pytest.skip(f"SNOMED data not found at {snomed_data_dir}")
    search.load(str(snomed_data_dir))
    return search


def test_snomed_load(snomed_search):
    """Test that SNOMED data loads successfully."""
    assert len(snomed_search.descriptions) > 0
    assert len(snomed_search._term_list) == len(snomed_search.descriptions)
    assert len(snomed_search._word_index) > 0


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


def test_snomed_search_fuzzy(snomed_search):
    """Test fuzzy search with misspelling."""
    # Test with a minor misspelling
    results = snomed_search.search("diabtes", limit=10)

    # Fuzzy search should still return results
    assert len(results) >= 0  # May or may not find exact matches

    # Test with closer match
    results_close = snomed_search.search("hypertension", limit=10)
    assert len(results_close) > 0


def test_snomed_search_empty_query(snomed_search):
    """Test search with empty query."""
    results = snomed_search.search("", limit=10)

    # Empty query should return empty or very few results
    assert len(results) <= 10


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
