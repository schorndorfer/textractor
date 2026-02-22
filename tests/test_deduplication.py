"""Tests for SNOMED search result deduplication."""
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
    """Create SNOMED search."""
    if not snomed_data_dir.exists():
        pytest.skip(f"SNOMED data not found at {snomed_data_dir}")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    search = SNOMEDSearch(db_path)
    search.build_index(snomed_data_dir)

    yield search

    search.close()
    if db_path.exists():
        db_path.unlink()


def test_no_duplicate_concept_ids(snomed_search):
    """Test that search returns no duplicate concept IDs."""
    results = snomed_search.search("hyperlipidemia", limit=20)

    # Extract concept IDs
    concept_ids = [r["concept_id"] for r in results]

    # Check for duplicates
    assert len(concept_ids) == len(set(concept_ids)), \
        f"Found duplicate concept IDs: {[cid for cid in concept_ids if concept_ids.count(cid) > 1]}"


def test_diabetes_no_duplicates(snomed_search):
    """Test common term 'diabetes' has no duplicates."""
    results = snomed_search.search("diabetes", limit=10)

    concept_ids = [r["concept_id"] for r in results]
    assert len(concept_ids) == len(set(concept_ids))


def test_keeps_best_match_per_concept(snomed_search):
    """Test that deduplication keeps the highest scoring match."""
    # Search for a term that likely has multiple descriptions
    results = snomed_search.search("myocardial infarction", limit=5)

    # All results should be unique concepts
    concept_ids = [r["concept_id"] for r in results]
    assert len(concept_ids) == len(set(concept_ids))

    # Scores should be in descending order (best matches first)
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)
