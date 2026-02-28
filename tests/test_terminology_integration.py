"""Integration tests for terminology search with SNOMED CT."""
import pytest
import tempfile
from pathlib import Path
from textractor.api.enhanced_terminology import EnhancedTerminologyIndex


@pytest.fixture(scope="session")
def snomed_dir():
    """Path to SNOMED CT data directory."""
    return Path(__file__).parent.parent / "data" / "terminology" / "SnomedCT"


@pytest.fixture(scope="session")
def enhanced_index(snomed_dir):
    """Create enhanced terminology index."""
    # Use temporary database for testing
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    index = EnhancedTerminologyIndex(db_path=db_path)

    if snomed_dir.exists():
        index.load_snomed(snomed_dir)

    yield index

    # Cleanup
    if db_path.exists():
        db_path.unlink()


def test_enhanced_index_snomed_loaded(enhanced_index, snomed_dir):
    """Test that SNOMED loads into enhanced index."""
    if not snomed_dir.exists():
        pytest.skip("SNOMED data not available")

    assert enhanced_index.is_loaded
    info = enhanced_index.info()
    assert info.loaded
    assert info.total_concepts > 0
    assert "SNOMED CT" in info.file_name


def test_enhanced_index_search_returns_terminology_concepts(enhanced_index, snomed_dir):
    """Test that search returns TerminologyConcept objects."""
    if not snomed_dir.exists():
        pytest.skip("SNOMED data not available")

    results = enhanced_index.search("myocardial infarction", limit=5)

    assert len(results) > 0
    assert len(results) <= 5

    # Check that results are TerminologyConcept objects with correct fields
    first = results[0]
    assert hasattr(first, "code")
    assert hasattr(first, "display")
    assert hasattr(first, "system")
    assert first.system == "SNOMED-CT"
    assert isinstance(first.code, str)
    assert isinstance(first.display, str)


def test_enhanced_index_search_diabetes(enhanced_index, snomed_dir):
    """Test search for diabetes."""
    if not snomed_dir.exists():
        pytest.skip("SNOMED data not available")

    results = enhanced_index.search("diabetes", limit=10)

    assert len(results) > 0
    result_displays = [r.display.lower() for r in results]
    assert any("diabetes" in display for display in result_displays)


def test_enhanced_index_without_snomed():
    """Test that index returns empty results when SNOMED not loaded."""
    index = EnhancedTerminologyIndex()

    # Don't load SNOMED - index should be empty
    assert not index.is_loaded

    info = index.info()
    assert not info.loaded
    assert info.total_concepts == 0

    results = index.search("test", limit=10)
    assert len(results) == 0


def test_enhanced_index_respects_limit(enhanced_index, snomed_dir):
    """Test that limit parameter is respected."""
    if not snomed_dir.exists():
        pytest.skip("SNOMED data not available")

    results_3 = enhanced_index.search("pain", limit=3)
    results_10 = enhanced_index.search("pain", limit=10)

    assert len(results_3) <= 3
    assert len(results_10) <= 10
    assert len(results_10) >= len(results_3)


def test_enhanced_terminology_load_icd10cm(tmp_path):
    """Load ICD-10-CM into EnhancedTerminologyIndex and search."""
    import csv
    from textractor.api.enhanced_terminology import EnhancedTerminologyIndex

    # Create synthetic file
    icd_file = tmp_path / "icd10cm_codes.txt"
    rows = [
        ("E1100", "Type 2 diabetes mellitus without complications"),
        ("I10", "Essential (primary) hypertension"),
        ("J189", "Pneumonia, unspecified organism"),
    ]
    with open(icd_file, "w") as f:
        writer = csv.writer(f, delimiter="\t")
        for r in rows:
            writer.writerow(r)

    db_path = tmp_path / "icd10cm.db"
    index = EnhancedTerminologyIndex(db_path=None, icd10cm_db_path=db_path)
    count = index.load_icd10cm(icd_file)

    assert count == 3
    assert index.icd10cm_loaded

    results = index.search("diabetes", limit=5, system="ICD-10-CM")
    assert len(results) > 0
    assert results[0].system == "ICD-10-CM"
    assert results[0].code == "E1100"


def test_enhanced_terminology_search_dispatches_by_system(tmp_path):
    """search() returns empty when no terminologies loaded."""
    from textractor.api.enhanced_terminology import EnhancedTerminologyIndex
    index = EnhancedTerminologyIndex()
    results = index.search("diabetes", limit=5, system="SNOMED-CT")
    assert results == []
    results2 = index.search("diabetes", limit=5, system="ICD-10-CM")
    assert results2 == []
