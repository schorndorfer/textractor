# ICD-10-CM Terminology Support Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add ICD-10-CM as a second searchable terminology alongside SNOMED CT, with a user-selectable dropdown in the annotation panel.

**Architecture:** Mirror the existing `SNOMEDSearch` SQLite FTS5 pattern with a new `ICD10CMSearch` class; extend `EnhancedTerminologyIndex` to dispatch searches by `system`; thread a `terminologySystem` state variable from `App.tsx` down to `ConceptSearch`.

**Tech Stack:** Python/SQLite FTS5 (backend), React/TypeScript (frontend), FastAPI, Vitest + pytest

**Issue:** https://github.com/schorndorfer/textractor/issues/89

---

## Background for the Implementer

### File layout to know
```
src/textractor/
  terminology/
    snomed.py           ← class SNOMEDSearch (FTS5 index builder + searcher)
  api/
    enhanced_terminology.py  ← class EnhancedTerminologyIndex (wraps SNOMEDSearch)
    dependencies.py          ← init_terminology(), module-level singletons
    models.py                ← Pydantic models incl. TerminologyInfo
    main.py                  ← FastAPI app factory, reads env vars in lifespan
    routers/
      terminology.py         ← GET /api/terminology/search, /api/terminology/info

frontend/src/
  types/index.ts        ← TypeScript interfaces (TerminologyConcept, TerminologyInfo)
  api/client.ts         ← searchTerminology(), getTerminologyInfo()
  constants.ts          ← SEARCH, UI, SIDEBAR, etc.
  App.tsx               ← all top-level state; passes props to AnnotationPanel
  components/
    ConceptSearch.tsx   ← debounced autocomplete for concept search
    AnnotationPanel.tsx ← renders SpanList + ReasoningStepList + DocumentAnnotationList

tests/
  test_snomed.py            ← unit tests for SNOMEDSearch (skip if no data)
  test_terminology_router.py ← API endpoint tests
```

### ICD-10-CM flat file format (CMS)
Tab-delimited, no header row:
```
A001\tCholera due to Vibrio cholerae 01, biovar cholerae
A002\tCholera due to Vibrio cholerae 01, biovar eltor
Z9981\tDependence on supplemental oxygen
```
~77,000 codes in the FY2025 file. Download from CMS and place at `data/terminology/icd10cm_codes.txt`.

### Key difference from SNOMED
SNOMED has `concept_id` (int) + `term` + `term_type` (FSN/SYNONYM) per row — multiple rows per concept.
ICD-10-CM has exactly one `code` (string like "A001") + `description` per row — one row per concept. No deduplication needed.

---

## Task 1: Create `ICD10CMSearch` class

**Files:**
- Create: `src/textractor/terminology/icd10cm.py`

**Step 1: Write the failing test first**

Create `tests/test_icd10cm.py`:

```python
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
```

**Step 2: Run the test — verify it fails**

```bash
uv run pytest tests/test_icd10cm.py -v 2>&1 | head -30
```
Expected: `ModuleNotFoundError` or `ImportError` — the module doesn't exist yet.

**Step 3: Implement `ICD10CMSearch`**

Create `src/textractor/terminology/icd10cm.py`:

```python
"""ICD-10-CM search using SQLite FTS5 full-text search."""
import csv
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ICD10CMSearch:
    """
    ICD-10-CM search using SQLite FTS5 for persistent storage and efficient searching.

    Features:
    - Persistent storage (no reload on restart)
    - Fast full-text search with FTS5 trigram tokenization
    - Custom relevance scoring (exact, prefix, word boundary, position-based)
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()

    def _get_connection(self) -> sqlite3.Connection:
        if self.conn is None:
            if self.db_path:
                self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            else:
                self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        return self.conn

    def build_index(self, file_path: Path) -> int:
        """
        Build SQLite FTS5 index from CMS ICD-10-CM flat file.

        Args:
            file_path: Path to tab-delimited file (no header): code TAB description

        Returns:
            Number of codes indexed
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS icd10cm_fts USING fts5(
                code,
                description,
                tokenize='trigram'
            )
        """)
        cursor.execute("DELETE FROM icd10cm_fts")

        count = 0
        batch = []
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="\t")
            for row in reader:
                if len(row) < 2:
                    continue
                code, description = row[0].strip(), row[1].strip()
                if code and description:
                    batch.append((code, description))
                    count += 1
                    if len(batch) >= 10000:
                        cursor.executemany(
                            "INSERT INTO icd10cm_fts (code, description) VALUES (?, ?)",
                            batch,
                        )
                        batch = []

        if batch:
            cursor.executemany(
                "INSERT INTO icd10cm_fts (code, description) VALUES (?, ?)",
                batch,
            )

        conn.commit()
        logger.info("Indexed %d ICD-10-CM codes in SQLite", count)
        return count

    def is_indexed(self) -> bool:
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM icd10cm_fts")
                return cursor.fetchone()[0] > 0
            except sqlite3.OperationalError:
                return False

    def _score_match(self, query: str, description: str, base_score: float) -> float:
        """Multi-factor scoring — identical logic to SNOMEDSearch._score_match."""
        query_lower = query.lower()
        desc_lower = description.lower()

        if query_lower == desc_lower:
            return base_score + 100
        if desc_lower.startswith(query_lower):
            return base_score + 80

        words = desc_lower.split()
        for i, word in enumerate(words):
            if word.startswith(query_lower):
                return base_score + max(60 - (i * 5), 30)

        if query_lower in desc_lower:
            position = desc_lower.index(query_lower)
            position_ratio = position / max(len(desc_lower), 1)
            return base_score + (40 - position_ratio * 20)

        return base_score

    def search(self, query: str, limit: int = 20) -> list[dict]:
        """
        Search ICD-10-CM descriptions using FTS5 full-text search.

        Returns list of dicts with keys: code, description, score
        """
        if not query.strip():
            return []

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            fts_query = f'"{query.strip()}"'

            cursor.execute("""
                SELECT code, description, rank
                FROM icd10cm_fts
                WHERE icd10cm_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (fts_query, limit * 3))

            results = cursor.fetchall()

            scored = []
            for code, description, fts_rank in results:
                base_score = abs(fts_rank)
                custom_score = self._score_match(query, description, base_score)
                scored.append({
                    "code": code,
                    "description": description,
                    "score": round(custom_score, 1),
                })

            scored.sort(key=lambda x: x["score"], reverse=True)
            return scored[:limit]

    def close(self):
        with self._lock:
            if self.conn:
                self.conn.close()
                self.conn = None

    def __del__(self):
        self.close()
```

**Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/test_icd10cm.py -v
```
Expected: All 8 tests PASS.

**Step 5: Commit**

```bash
git add src/textractor/terminology/icd10cm.py tests/test_icd10cm.py
git commit -m "feat: add ICD10CMSearch class with SQLite FTS5 index (issue #89)"
```

---

## Task 2: Extend `TerminologyInfo` model to support multiple systems

**Files:**
- Modify: `src/textractor/api/models.py`
- Modify: `frontend/src/types/index.ts`

**Why now:** Both backend and frontend tests against the new `info` shape should exist before wiring things up.

**Step 1: Write failing backend model test**

Add to `tests/test_models.py` (or create if tiny):

```python
# Add at the bottom of tests/test_models.py
def test_terminology_info_has_systems_field():
    from textractor.api.models import TerminologyInfo, TerminologySystemInfo
    info = TerminologyInfo(
        total_concepts=100,
        file_name="test",
        loaded=True,
        systems=[
            TerminologySystemInfo(system="SNOMED-CT", loaded=True, count=100),
            TerminologySystemInfo(system="ICD-10-CM", loaded=False, count=None),
        ]
    )
    assert len(info.systems) == 2
    assert info.systems[0].system == "SNOMED-CT"
    assert info.systems[1].loaded is False
```

**Step 2: Run to verify failure**

```bash
uv run pytest tests/test_models.py -v -k "test_terminology_info_has_systems_field"
```
Expected: FAIL — `TerminologySystemInfo` doesn't exist.

**Step 3: Update `models.py`**

In `src/textractor/api/models.py`, add `TerminologySystemInfo` and extend `TerminologyInfo`:

```python
class TerminologySystemInfo(BaseModel):
    system: str          # e.g. "SNOMED-CT", "ICD-10-CM"
    loaded: bool
    count: Optional[int] = None


class TerminologyInfo(BaseModel):
    total_concepts: int
    file_name: Optional[str]
    loaded: bool
    systems: list[TerminologySystemInfo] = Field(default_factory=list)
```

**Step 4: Run test — verify pass**

```bash
uv run pytest tests/test_models.py -v -k "test_terminology_info_has_systems_field"
```
Expected: PASS.

**Step 5: Commit**

```bash
git add src/textractor/api/models.py tests/test_models.py
git commit -m "feat: extend TerminologyInfo model with systems list (issue #89)"
```

---

## Task 3: Extend `EnhancedTerminologyIndex` with ICD-10-CM support

**Files:**
- Modify: `src/textractor/api/enhanced_terminology.py`

**Step 1: Write failing test**

Add to `tests/test_terminology_integration.py` (append at bottom after reading the file):

```python
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
    """search() with system=None returns empty when no SNOMED loaded."""
    from textractor.api.enhanced_terminology import EnhancedTerminologyIndex
    index = EnhancedTerminologyIndex()
    results = index.search("diabetes", limit=5, system="SNOMED-CT")
    assert results == []
    results2 = index.search("diabetes", limit=5, system="ICD-10-CM")
    assert results2 == []
```

**Step 2: Run to verify failure**

```bash
uv run pytest tests/test_terminology_integration.py -v -k "icd10cm"
```
Expected: FAIL — `icd10cm_loaded` attribute and `load_icd10cm` method don't exist.

**Step 3: Update `enhanced_terminology.py`**

Replace the entire file with the extended version:

```python
"""Terminology search supporting SNOMED CT and ICD-10-CM."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Protocol

from .models import TerminologyConcept, TerminologyInfo, TerminologySystemInfo

logger = logging.getLogger(__name__)


class SNOMEDSearchProtocol(Protocol):
    def search(self, query: str, limit: int) -> list[dict]: ...
    def is_indexed(self) -> bool: ...


class ICD10CMSearchProtocol(Protocol):
    def search(self, query: str, limit: int) -> list[dict]: ...
    def is_indexed(self) -> bool: ...


class EnhancedTerminologyIndex:
    """
    Terminology search supporting SNOMED CT and ICD-10-CM.

    Search is dispatched to the correct backend based on the `system` parameter.
    Both systems can be loaded independently; either or both may be absent.
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,           # SNOMED DB path
        icd10cm_db_path: Optional[Path] = None,   # ICD-10-CM DB path
    ) -> None:
        # SNOMED state
        self._snomed_search: Optional[SNOMEDSearchProtocol] = None
        self._snomed_loaded = False
        self._snomed_count: Optional[int] = None
        self._snomed_path: Optional[str] = None
        self._db_path = db_path

        # ICD-10-CM state
        self._icd10cm_search: Optional[ICD10CMSearchProtocol] = None
        self._icd10cm_loaded = False
        self._icd10cm_count: Optional[int] = None
        self._icd10cm_db_path = icd10cm_db_path

    @property
    def is_loaded(self) -> bool:
        return self._snomed_loaded or self._icd10cm_loaded

    @property
    def icd10cm_loaded(self) -> bool:
        return self._icd10cm_loaded

    @property
    def snomed_loaded(self) -> bool:
        return self._snomed_loaded

    def info(self) -> TerminologyInfo:
        systems: list[TerminologySystemInfo] = [
            TerminologySystemInfo(
                system="SNOMED-CT",
                loaded=self._snomed_loaded,
                count=self._snomed_count,
            ),
            TerminologySystemInfo(
                system="ICD-10-CM",
                loaded=self._icd10cm_loaded,
                count=self._icd10cm_count,
            ),
        ]

        total = (self._snomed_count or 0) + (self._icd10cm_count or 0)
        loaded = self._snomed_loaded or self._icd10cm_loaded

        file_name_parts = []
        if self._snomed_loaded and self._snomed_count:
            file_name_parts.append(f"SNOMED CT ({self._snomed_count} descriptions)")
        if self._icd10cm_loaded and self._icd10cm_count:
            file_name_parts.append(f"ICD-10-CM ({self._icd10cm_count} codes)")

        return TerminologyInfo(
            total_concepts=total,
            file_name=", ".join(file_name_parts) if file_name_parts else None,
            loaded=loaded,
            systems=systems,
        )

    # ── SNOMED loading ────────────────────────────────────────────────────────

    def load_snomed(self, rf2_dir: Path) -> int:
        desc_count = self._try_load_snomed_sqlite(rf2_dir)
        self._snomed_count = desc_count if desc_count > 0 else None
        return desc_count

    def _try_load_snomed_sqlite(self, rf2_dir: Path) -> int:
        if not self._db_path:
            logger.warning("No database path provided for SNOMED loading")
            return 0
        try:
            from textractor.terminology.snomed import SNOMEDSearch

            self._snomed_search = SNOMEDSearch(self._db_path)
            if self._snomed_search.is_indexed():
                logger.info("Using existing SNOMED database at %s", self._db_path)
                conn = self._snomed_search._get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM snomed_fts")
                desc_count = cursor.fetchone()[0]
            else:
                logger.info("Building SNOMED index from %s", rf2_dir)
                desc_count = self._snomed_search.build_index(rf2_dir)
                logger.info("Built SNOMED index with %d descriptions", desc_count)

            self._snomed_loaded = True
            self._snomed_path = str(rf2_dir)
            return desc_count
        except Exception as exc:
            logger.error("Failed to load SNOMED CT from %s: %s", rf2_dir, exc)
            return 0

    # ── ICD-10-CM loading ─────────────────────────────────────────────────────

    def load_icd10cm(self, file_path: Path) -> int:
        """
        Load ICD-10-CM from CMS flat file into SQLite database.

        Args:
            file_path: Path to tab-delimited ICD-10-CM flat file
        Returns:
            Number of codes indexed (0 on failure)
        """
        count = self._try_load_icd10cm_sqlite(file_path)
        self._icd10cm_count = count if count > 0 else None
        return count

    def _try_load_icd10cm_sqlite(self, file_path: Path) -> int:
        if not self._icd10cm_db_path:
            logger.warning("No ICD-10-CM database path provided")
            return 0
        try:
            from textractor.terminology.icd10cm import ICD10CMSearch

            self._icd10cm_search = ICD10CMSearch(self._icd10cm_db_path)
            if self._icd10cm_search.is_indexed():
                logger.info("Using existing ICD-10-CM database at %s", self._icd10cm_db_path)
                # Count via direct connection access
                conn = self._icd10cm_search._get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM icd10cm_fts")
                count = cursor.fetchone()[0]
            else:
                logger.info("Building ICD-10-CM index from %s", file_path)
                count = self._icd10cm_search.build_index(file_path)
                logger.info("Built ICD-10-CM index with %d codes", count)

            self._icd10cm_loaded = True
            return count
        except Exception as exc:
            logger.error("Failed to load ICD-10-CM from %s: %s", file_path, exc)
            return 0

    # ── Search ────────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        limit: int = 20,
        system: Optional[str] = None,
    ) -> list[TerminologyConcept]:
        """
        Search terminology concepts.

        Args:
            query: Search string
            limit: Max results
            system: "SNOMED-CT", "ICD-10-CM", or None (defaults to SNOMED-CT)
        """
        target = system or "SNOMED-CT"

        if target == "ICD-10-CM":
            return self._search_icd10cm(query, limit)
        return self._search_snomed(query, limit)

    def _search_snomed(self, query: str, limit: int) -> list[TerminologyConcept]:
        if not self._snomed_loaded or not self._snomed_search:
            return []
        results = self._snomed_search.search(query, limit=limit)
        return [
            TerminologyConcept(
                code=str(r["concept_id"]),
                display=r["term"],
                system="SNOMED-CT",
            )
            for r in results
        ]

    def _search_icd10cm(self, query: str, limit: int) -> list[TerminologyConcept]:
        if not self._icd10cm_loaded or not self._icd10cm_search:
            return []
        results = self._icd10cm_search.search(query, limit=limit)
        return [
            TerminologyConcept(
                code=r["code"],
                display=r["description"],
                system="ICD-10-CM",
            )
            for r in results
        ]
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_terminology_integration.py -v
uv run pytest tests/test_terminology_router.py -v
```
Expected: All PASS (existing router tests still pass because `search()` defaults to SNOMED-CT behavior).

**Step 5: Commit**

```bash
git add src/textractor/api/enhanced_terminology.py tests/test_terminology_integration.py
git commit -m "feat: extend EnhancedTerminologyIndex with ICD-10-CM support (issue #89)"
```

---

## Task 4: Update `dependencies.py` and `main.py` for ICD-10-CM env var

**Files:**
- Modify: `src/textractor/api/dependencies.py`
- Modify: `src/textractor/api/main.py`

**Step 1: Update `init_terminology` signature and body in `dependencies.py`**

```python
def init_terminology(
    snomed_dir: Optional[Path] = None,
    icd10cm_file: Optional[Path] = None,
) -> None:
    """
    Initialize terminology indices (SNOMED CT and/or ICD-10-CM).

    Args:
        snomed_dir: Optional path to SNOMED CT RF2 directory
        icd10cm_file: Optional path to CMS ICD-10-CM flat file
    """
    global _terminology

    db_path = None
    if snomed_dir and snomed_dir.exists():
        db_path = snomed_dir.parent / "snomed.db"

    icd10cm_db_path = None
    if icd10cm_file and icd10cm_file.exists():
        icd10cm_db_path = icd10cm_file.parent / "icd10cm.db"

    _terminology = EnhancedTerminologyIndex(
        db_path=db_path,
        icd10cm_db_path=icd10cm_db_path,
    )

    if snomed_dir and snomed_dir.exists():
        count = _terminology.load_snomed(snomed_dir)
        if count > 0:
            logger.info("Loaded SNOMED CT with %d active descriptions", count)
        else:
            logger.warning("Failed to load SNOMED CT from %s", snomed_dir)
    else:
        logger.info("No SNOMED directory provided — SNOMED search unavailable")

    if icd10cm_file and icd10cm_file.exists():
        count = _terminology.load_icd10cm(icd10cm_file)
        if count > 0:
            logger.info("Loaded ICD-10-CM with %d codes", count)
        else:
            logger.warning("Failed to load ICD-10-CM from %s", icd10cm_file)
    else:
        logger.info("No ICD-10-CM file provided — ICD-10-CM search unavailable")
```

**Step 2: Update `main.py` lifespan to read the new env var**

In the `lifespan` function, add:

```python
icd10cm_file_path = os.environ.get("TEXTRACTOR_ICD10CM_FILE", "./data/terminology/icd10cm_codes.txt")
icd10cm_file = Path(icd10cm_file_path) if icd10cm_file_path else None

init_terminology(snomed_dir=snomed_dir, icd10cm_file=icd10cm_file)
```

**Step 3: Run all backend tests**

```bash
uv run pytest tests/ -v --ignore=tests/test_snomed.py -x
```
Expected: All PASS. (`test_snomed.py` is skipped because no SNOMED data in CI.)

**Step 4: Commit**

```bash
git add src/textractor/api/dependencies.py src/textractor/api/main.py
git commit -m "feat: read TEXTRACTOR_ICD10CM_FILE env var and load ICD-10-CM on startup (issue #89)"
```

---

## Task 5: Update terminology API router with `system` query param

**Files:**
- Modify: `src/textractor/api/routers/terminology.py`
- Modify: `tests/test_terminology_router.py`

**Step 1: Write failing tests**

Append to `tests/test_terminology_router.py`:

```python
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
```

**Step 2: Run to verify failure**

```bash
uv run pytest tests/test_terminology_router.py -v -k "TestSystemParameter"
```
Expected: FAIL — `system` param not accepted, `systems` field missing from `info`.

**Step 3: Update router**

Replace `src/textractor/api/routers/terminology.py`:

```python
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query

from ..dependencies import get_terminology
from ..enhanced_terminology import EnhancedTerminologyIndex
from ..models import TerminologyConcept, TerminologyInfo

router = APIRouter(prefix="/api/terminology", tags=["terminology"])

VALID_SYSTEMS = {"SNOMED-CT", "ICD-10-CM"}


@router.get("/search", response_model=list[TerminologyConcept])
def search_concepts(
    q: str = Query(default="", description="Terminology search query"),
    limit: int = Query(default=20, ge=1, le=200),
    system: Optional[str] = Query(
        default=None,
        description="Terminology system: SNOMED-CT or ICD-10-CM",
    ),
    index: EnhancedTerminologyIndex = Depends(get_terminology),
) -> list[TerminologyConcept]:
    """Search terminology using full-text search."""
    if system is not None and system not in VALID_SYSTEMS:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=422,
            detail=f"system must be one of: {sorted(VALID_SYSTEMS)}",
        )
    return index.search(q, limit=limit, system=system)


@router.get("/info", response_model=TerminologyInfo)
def terminology_info(
    index: EnhancedTerminologyIndex = Depends(get_terminology),
) -> TerminologyInfo:
    """Get information about all loaded terminology systems."""
    return index.info()
```

**Step 4: Run all router tests**

```bash
uv run pytest tests/test_terminology_router.py -v
```
Expected: All PASS.

**Step 5: Run all backend tests**

```bash
uv run pytest tests/ -v --ignore=tests/test_snomed.py -x
```
Expected: All PASS.

**Step 6: Commit**

```bash
git add src/textractor/api/routers/terminology.py tests/test_terminology_router.py
git commit -m "feat: add system query param to terminology search endpoint (issue #89)"
```

---

## Task 6: Update frontend API client and types

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/types/index.ts`

**Step 1: Update `types/index.ts`**

Add `TerminologySystemInfo` and extend `TerminologyInfo`:

```typescript
export interface TerminologySystemInfo {
  system: string;
  loaded: boolean;
  count: number | null;
}

export interface TerminologyInfo {
  total_concepts: number;
  file_name: string | null;
  loaded: boolean;
  systems: TerminologySystemInfo[];
}
```

**Step 2: Update `api/client.ts` — add `system` param to `searchTerminology`**

Change the `searchTerminology` entry from:
```typescript
searchTerminology: (q: string, limit = 20) =>
  request<TerminologyConcept[]>(
    `/terminology/search?q=${encodeURIComponent(q)}&limit=${limit}`
  ),
```
To:
```typescript
searchTerminology: (q: string, limit = 20, system?: string) => {
  const params = new URLSearchParams({ q, limit: String(limit) });
  if (system) params.set('system', system);
  return request<TerminologyConcept[]>(`/terminology/search?${params}`);
},
```

**Step 3: Run frontend tests to verify no breakage**

```bash
cd frontend && npm test -- --run 2>&1 | tail -20
```
Expected: All 29 tests PASS.

**Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/client.ts
git commit -m "feat: add system param to searchTerminology and update TerminologyInfo type (issue #89)"
```

---

## Task 7: Add terminology selector state to `App.tsx` and fetch available systems

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/AnnotationPanel.tsx`

**Step 1: Add state + effect to `App.tsx`**

Add after the existing state declarations (around line 28):

```typescript
const [terminologySystem, setTerminologySystem] = useState<string>('SNOMED-CT');
const [availableSystems, setAvailableSystems] = useState<string[]>(['SNOMED-CT', 'ICD-10-CM']);
```

Add a `useEffect` to fetch available systems on mount (after the existing `refreshDocuments` effect):

```typescript
useEffect(() => {
  api.getTerminologyInfo().then((info) => {
    const loaded = info.systems
      .filter((s) => s.loaded)
      .map((s) => s.system);
    if (loaded.length > 0) {
      setAvailableSystems(loaded);
      // Default to first available system
      setTerminologySystem(loaded[0]);
    }
  }).catch(() => {
    // Keep defaults on error
  });
}, []);
```

**Step 2: Pass new props to `AnnotationPanel`**

In the `AnnotationPanel` JSX block (around line 443), add:

```tsx
terminologySystem={terminologySystem}
onTerminologyChange={setTerminologySystem}
availableSystems={availableSystems}
```

**Step 3: Update `AnnotationPanel.tsx` Props interface and component**

Add to `Props` interface:
```typescript
terminologySystem: string;
onTerminologyChange: (system: string) => void;
availableSystems: string[];
```

Add destructuring in the component function.

In the `AnnotationPanel` JSX header (where Pre-annotate button lives), add the selector:

```tsx
<select
  className="terminology-selector"
  value={terminologySystem}
  onChange={(e) => onTerminologyChange(e.target.value)}
  disabled={availableSystems.length <= 1}
  title="Select terminology system for concept search"
>
  {availableSystems.map((sys) => (
    <option key={sys} value={sys}>{sys}</option>
  ))}
</select>
```

**Step 4: Run frontend tests**

```bash
cd frontend && npm test -- --run 2>&1 | tail -20
```
Expected: All tests PASS (AnnotationPanel tests use mocked props, so adding optional ones doesn't break them — but verify).

**Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/AnnotationPanel.tsx
git commit -m "feat: add terminology system selector dropdown in annotation panel (issue #89)"
```

---

## Task 8: Thread `system` prop through to `ConceptSearch`

**Files:**
- Modify: `frontend/src/components/ConceptSearch.tsx`
- Modify: `frontend/src/components/ReasoningStepList.tsx`
- Modify: `frontend/src/components/DocumentAnnotationList.tsx`
- Modify: `frontend/src/components/AnnotationPanel.tsx`

**Step 1: Update `ConceptSearch` props**

Add `system?: string` to the `Props` interface:
```typescript
interface Props {
  value: TerminologyConcept | null;
  onChange: (concept: TerminologyConcept | null) => void;
  placeholder?: string;
  system?: string;
}
```

In `performSearch`, pass `system`:
```typescript
const hits = await api.searchTerminology(q, SEARCH.DEFAULT_LIMIT, system);
```

**Step 2: Update `ReasoningStepList.tsx`**

Find where `ConceptSearch` is rendered and check what props it receives. Add `system` prop forwarding.

First read the file to understand the exact prop chain:
```bash
grep -n "ConceptSearch" frontend/src/components/ReasoningStepList.tsx
```

Add `system?: string` to `ReasoningStepList`'s Props interface and pass it down to each `ConceptSearch`.

**Step 3: Update `DocumentAnnotationList.tsx`**

Same pattern — add `system` to its Props and pass to `ConceptSearch`.

**Step 4: Update `AnnotationPanel.tsx`**

Pass `terminologySystem` as `system` prop to both `ReasoningStepList` and `DocumentAnnotationList`.

**Step 5: Run frontend tests**

```bash
cd frontend && npm test -- --run 2>&1 | tail -20
```
Expected: All 29 PASS.

**Step 6: Commit**

```bash
git add frontend/src/components/ConceptSearch.tsx \
        frontend/src/components/ReasoningStepList.tsx \
        frontend/src/components/DocumentAnnotationList.tsx \
        frontend/src/components/AnnotationPanel.tsx
git commit -m "feat: thread system prop through ConceptSearch for ICD-10-CM selection (issue #89)"
```

---

## Task 9: Update CLAUDE.md and environment variable table

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Add ICD-10-CM to the environment variables table**

In the **Storage Configuration** table, add:

| `TEXTRACTOR_ICD10CM_FILE` | `./data/terminology/icd10cm_codes.txt` | Path to CMS ICD-10-CM tab-delimited flat file |

**Step 2: Add ICD-10-CM to the architecture section**

In the **SNOMED CT Terminology** section (or alongside it), add a note:

> **ICD-10-CM integration** — place the CMS flat file (e.g. `icd10cm_codes_2025.txt`) at `data/terminology/icd10cm_codes.txt` (or path specified by `TEXTRACTOR_ICD10CM_FILE`). SQLite database built at `data/terminology/icd10cm.db` on first startup.

**Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document ICD-10-CM env var and setup in CLAUDE.md (issue #89)"
```

---

## Task 10: Final verification pass

**Step 1: Run full backend test suite**

```bash
uv run pytest tests/ -v --ignore=tests/test_snomed.py 2>&1 | tail -30
```
Expected: All PASS.

**Step 2: Run full frontend test suite**

```bash
cd frontend && npm test -- --run 2>&1 | tail -20
```
Expected: All 29 PASS.

**Step 3: Manual smoke test (if server available)**

```bash
# Terminal 1
TEXTRACTOR_DOC_ROOT=./data/documents uv run textractor

# Terminal 2
curl "http://localhost:8000/api/terminology/info" | python3 -m json.tool
# Should see systems array with SNOMED-CT and ICD-10-CM entries

curl "http://localhost:8000/api/terminology/search?q=diabetes&system=SNOMED-CT" | python3 -m json.tool
curl "http://localhost:8000/api/terminology/search?q=diabetes&system=ICD-10-CM" | python3 -m json.tool
```

**Step 4: Create PR**

```bash
git push -u origin feat/icd10cm-terminology-support
gh pr create \
  --title "feat: Add ICD-10-CM terminology support with system selector dropdown" \
  --body "Closes #89" \
  --base master
```

---

## Summary of All Changed Files

| File | Change |
|---|---|
| `src/textractor/terminology/icd10cm.py` | **New** — `ICD10CMSearch` class |
| `src/textractor/api/models.py` | Add `TerminologySystemInfo`, extend `TerminologyInfo.systems` |
| `src/textractor/api/enhanced_terminology.py` | Add ICD-10-CM loading + dispatch by `system` |
| `src/textractor/api/dependencies.py` | Add `icd10cm_file` param to `init_terminology` |
| `src/textractor/api/main.py` | Read `TEXTRACTOR_ICD10CM_FILE` env var |
| `src/textractor/api/routers/terminology.py` | Add `system` query param, validate allowed values |
| `frontend/src/types/index.ts` | Add `TerminologySystemInfo`, extend `TerminologyInfo` |
| `frontend/src/api/client.ts` | Add `system` param to `searchTerminology` |
| `frontend/src/App.tsx` | `terminologySystem` + `availableSystems` state, fetch info on mount |
| `frontend/src/components/AnnotationPanel.tsx` | Terminology selector dropdown, pass props down |
| `frontend/src/components/ConceptSearch.tsx` | Accept `system` prop, pass to API call |
| `frontend/src/components/ReasoningStepList.tsx` | Forward `system` prop |
| `frontend/src/components/DocumentAnnotationList.tsx` | Forward `system` prop |
| `tests/test_icd10cm.py` | **New** — unit tests for `ICD10CMSearch` |
| `tests/test_terminology_router.py` | Add `TestSystemParameter` class |
| `tests/test_terminology_integration.py` | Add ICD-10-CM integration tests |
| `tests/test_models.py` | Add `TerminologySystemInfo` test |
| `CLAUDE.md` | Document new env var and ICD-10-CM setup |
