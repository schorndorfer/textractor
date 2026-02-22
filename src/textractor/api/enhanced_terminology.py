"""Enhanced terminology search using SNOMED CT when available, with TSV fallback."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Protocol

from .models import TerminologyConcept, TerminologyInfo
from .terminology import TerminologyIndex

logger = logging.getLogger(__name__)


class SNOMEDSearchProtocol(Protocol):
    """Protocol defining the interface for SNOMED search implementations."""

    def search(self, query: str, limit: int) -> list[dict]:
        """Search for SNOMED concepts."""
        ...

    def is_indexed(self) -> bool:
        """Check if the search index is ready."""
        ...


class EnhancedTerminologyIndex:
    """
    Terminology search with fallback options:
    1. SNOMED CT (SQLite FTS5 - persistent, fast, low memory)
    2. TSV (simple, limited)
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._snomed_search: Optional[SNOMEDSearchProtocol] = None
        self._tsv_index = TerminologyIndex()
        self._snomed_loaded = False
        self._snomed_count: Optional[int] = None
        self._snomed_path: Optional[str] = None
        self._db_path = db_path

    @property
    def is_loaded(self) -> bool:
        return self._snomed_loaded or self._tsv_index.is_loaded

    def info(self) -> TerminologyInfo:
        if self._snomed_loaded and self._snomed_count is not None:
            return TerminologyInfo(
                total_concepts=self._snomed_count,
                file_name=f"SNOMED CT ({self._snomed_count} descriptions)",
                loaded=True,
            )
        return self._tsv_index.info()

    def load_snomed(self, rf2_dir: Path) -> int:
        """
        Load SNOMED CT from RF2 files into SQLite database.

        If database already exists, it will be reused. Otherwise, it will be built
        from the RF2 files in the provided directory.
        """
        desc_count = self._try_load_sqlite(rf2_dir)
        self._snomed_count = desc_count if desc_count > 0 else None
        return desc_count

    def _try_load_sqlite(self, rf2_dir: Path) -> int:
        """Load SNOMED using SQLite. Returns 0 on failure."""
        if not self._db_path:
            logger.warning("No database path provided for SNOMED loading")
            return 0

        try:
            from textractor.terminology.snomed import SNOMEDSearch

            self._snomed_search = SNOMEDSearch(self._db_path)

            # Check if database is already indexed
            if self._snomed_search.is_indexed():
                logger.info("Using existing SNOMED database at %s", self._db_path)
                conn = self._snomed_search._get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM snomed_fts")
                desc_count = cursor.fetchone()[0]
            else:
                # Build index from RF2 files
                logger.info("Building SNOMED index from %s", rf2_dir)
                desc_count = self._snomed_search.build_index(rf2_dir)
                logger.info("Built SNOMED index with %d descriptions", desc_count)

            self._snomed_loaded = True
            self._snomed_path = str(rf2_dir)
            return desc_count

        except Exception as exc:
            logger.error("Failed to load SNOMED CT from %s: %s", rf2_dir, exc)
            return 0

    def load_from_path(self, path: Path) -> int:
        """Load TSV terminology file (fallback)."""
        return self._tsv_index.load_from_path(path)

    def load_from_bytes(self, data: bytes, filename: str) -> int:
        """Load TSV terminology from bytes (for file upload)."""
        return self._tsv_index.load_from_bytes(data, filename)

    def search(self, query: str, limit: int = 20) -> list[TerminologyConcept]:
        """
        Search for concepts. Uses SNOMED CT if loaded, otherwise TSV index.
        """
        if self._snomed_loaded and self._snomed_search:
            return self._search_snomed(query, limit)
        return self._tsv_index.search(query, limit)

    def _search_snomed(self, query: str, limit: int) -> list[TerminologyConcept]:
        """Search using SNOMED CT and convert to TerminologyConcept."""
        if not self._snomed_search:
            return []

        results = self._snomed_search.search(query, limit=limit)

        # Convert SNOMED search results to TerminologyConcept format
        concepts = []
        for result in results:
            concept = TerminologyConcept(
                code=str(result["concept_id"]),
                display=result["term"],
                system="SNOMED-CT",
            )
            concepts.append(concept)

        return concepts
