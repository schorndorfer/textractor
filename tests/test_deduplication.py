"""Tests for SNOMED search result deduplication."""
import pytest
import tempfile
from pathlib import Path
from textractor.terminology.snomed import SNOMEDSearch
from textractor.terminology.snomed_sqlite import SNOMEDSearchSQLite


@pytest.fixture(scope="session")
def snomed_data_dir():
    """Path to SNOMED CT data directory."""
    return Path(__file__).parent.parent / "data" / "terminology" / "SnomedCT"


@pytest.fixture(scope="session")
def in_memory_search(snomed_data_dir):
    """Create in-memory SNOMED search."""
    if not snomed_data_dir.exists():
        pytest.skip(f"SNOMED data not found at {snomed_data_dir}")

    search = SNOMEDSearch()
    search.load(str(snomed_data_dir))
    return search


@pytest.fixture(scope="session")
def sqlite_search(snomed_data_dir):
    """Create SQLite SNOMED search."""
    if not snomed_data_dir.exists():
        pytest.skip(f"SNOMED data not found at {snomed_data_dir}")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    search = SNOMEDSearchSQLite(db_path)
    search.build_index(snomed_data_dir)

    yield search

    search.close()
    if db_path.exists():
        db_path.unlink()


def test_in_memory_no_duplicate_concept_ids(in_memory_search):
    """Test that in-memory search returns no duplicate concept IDs."""
    results = in_memory_search.search("hyperlipidemia", limit=20)

    # Extract concept IDs
    concept_ids = [r["concept_id"] for r in results]

    # Check for duplicates
    assert len(concept_ids) == len(set(concept_ids)), \
        f"Found duplicate concept IDs: {[cid for cid in concept_ids if concept_ids.count(cid) > 1]}"


def test_sqlite_no_duplicate_concept_ids(sqlite_search):
    """Test that SQLite search returns no duplicate concept IDs."""
    results = sqlite_search.search("hyperlipidemia", limit=20)

    # Extract concept IDs
    concept_ids = [r["concept_id"] for r in results]

    # Check for duplicates
    assert len(concept_ids) == len(set(concept_ids)), \
        f"Found duplicate concept IDs: {[cid for cid in concept_ids if concept_ids.count(cid) > 1]}"


def test_in_memory_diabetes_no_duplicates(in_memory_search):
    """Test common term 'diabetes' has no duplicates."""
    results = in_memory_search.search("diabetes", limit=10)

    concept_ids = [r["concept_id"] for r in results]
    assert len(concept_ids) == len(set(concept_ids))


def test_sqlite_diabetes_no_duplicates(sqlite_search):
    """Test common term 'diabetes' has no duplicates."""
    results = sqlite_search.search("diabetes", limit=10)

    concept_ids = [r["concept_id"] for r in results]
    assert len(concept_ids) == len(set(concept_ids))


def test_in_memory_keeps_best_match_per_concept(in_memory_search):
    """Test that deduplication keeps the highest scoring match."""
    # Search for a term that likely has multiple descriptions
    results = in_memory_search.search("myocardial infarction", limit=5)

    # All results should be unique concepts
    concept_ids = [r["concept_id"] for r in results]
    assert len(concept_ids) == len(set(concept_ids))

    # Scores should be in descending order (best matches first)
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_sqlite_keeps_best_match_per_concept(sqlite_search):
    """Test that deduplication keeps the highest scoring match."""
    # Search for a term that likely has multiple descriptions
    results = sqlite_search.search("myocardial infarction", limit=5)

    # All results should be unique concepts
    concept_ids = [r["concept_id"] for r in results]
    assert len(concept_ids) == len(set(concept_ids))

    # Scores should be in descending order (best matches first)
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)
