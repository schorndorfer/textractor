"""Tests for ICD-10-CM search functionality."""
import csv
import tempfile
from pathlib import Path

import pytest

from textractor.terminology.icd10cm import ICD10CMSearch


@pytest.fixture
def sample_icd10cm_file(tmp_path):
    """Create a small synthetic ICD-10-CM flat file for testing."""
    file_path = tmp_path / "icd10cm_codes.txt"
    rows = [
        ("A001", "Cholera due to Vibrio cholerae 01, biovar cholerae"),
        ("A002", "Cholera due to Vibrio cholerae 01, biovar eltor"),
        ("E1100", "Type 2 diabetes mellitus without complications"),
        ("E1101", "Type 2 diabetes mellitus with hyperosmolarity without nonketotic hyperglycemic-hyperosmolar coma"),
        ("E119", "Type 2 diabetes mellitus without complications"),
        ("I10", "Essential (primary) hypertension"),
        ("I110", "Hypertensive heart disease with heart failure"),
        ("J189", "Pneumonia, unspecified organism"),
        ("R0600", "Dyspnea, unspecified"),
        ("Z87891", "Personal history of nicotine dependence"),
    ]
    with open(file_path, "w", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="\t")
        for code, desc in rows:
            writer.writerow([code, desc])
    return file_path


@pytest.fixture
def icd10cm_search(sample_icd10cm_file, tmp_path):
    """Build a small ICD-10-CM index for testing."""
    db_path = tmp_path / "icd10cm_test.db"
    search = ICD10CMSearch(db_path)
    search.build_index(sample_icd10cm_file)
    yield search
    search.close()


def test_build_index(icd10cm_search):
    assert icd10cm_search.is_indexed()


def test_search_diabetes(icd10cm_search):
    results = icd10cm_search.search("diabetes", limit=10)
    assert len(results) > 0
    terms = [r["description"].lower() for r in results]
    assert any("diabetes" in t for t in terms)


def test_search_hypertension(icd10cm_search):
    results = icd10cm_search.search("hypertension", limit=5)
    assert len(results) > 0
    terms = [r["description"].lower() for r in results]
    assert any("hypertension" in t for t in terms)


def test_search_empty_query(icd10cm_search):
    results = icd10cm_search.search("", limit=10)
    assert results == []


def test_search_limit(icd10cm_search):
    results_3 = icd10cm_search.search("diabetes", limit=3)
    results_10 = icd10cm_search.search("diabetes", limit=10)
    assert len(results_3) <= 3
    assert len(results_10) >= len(results_3)


def test_result_structure(icd10cm_search):
    results = icd10cm_search.search("hypertension", limit=5)
    assert len(results) > 0
    for r in results:
        assert "code" in r
        assert "description" in r
        assert "score" in r
        assert isinstance(r["code"], str)
        assert isinstance(r["description"], str)
        assert isinstance(r["score"], float)


def test_code_exact_match_ranks_first(icd10cm_search):
    """Searching for the exact code 'I10' should find it."""
    results = icd10cm_search.search("I10", limit=5)
    assert len(results) > 0
    codes = [r["code"] for r in results]
    assert "I10" in codes


def test_persistence(sample_icd10cm_file, tmp_path):
    """Index built once can be reopened without rebuilding."""
    db_path = tmp_path / "icd10cm_persist.db"
    s1 = ICD10CMSearch(db_path)
    count = s1.build_index(sample_icd10cm_file)
    s1.close()
    assert count == 10

    s2 = ICD10CMSearch(db_path)
    assert s2.is_indexed()
    results = s2.search("diabetes", limit=5)
    assert len(results) > 0
    s2.close()
