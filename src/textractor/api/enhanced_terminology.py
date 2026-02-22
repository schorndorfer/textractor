"""Enhanced terminology search using SNOMED CT when available, with TSV fallback."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .models import TerminologyConcept, TerminologyInfo
from .terminology import TerminologyIndex

logger = logging.getLogger(__name__)


class EnhancedTerminologyIndex:
    """
    Terminology search with multiple fallback options:
    1. SQLite FTS5 (persistent, fast, low memory)
    2. In-memory SNOMED (fast, high memory)
    3. TSV (simple, limited)
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._snomed_search: Optional[object] = None  # SNOMEDSearch or SNOMEDSearchSQLite
        self._tsv_index = TerminologyIndex()
        self._snomed_loaded = False
        self._snomed_path: Optional[str] = None
        self._db_path = db_path
        self._using_sqlite = False

    @property
    def is_loaded(self) -> bool:
        return self._snomed_loaded or self._tsv_index.is_loaded

    def info(self) -> TerminologyInfo:
        if self._snomed_loaded and self._snomed_search:
            # Get description count from SNOMED
            if self._using_sqlite:
                # For SQLite, query the count
                try:
                    conn = self._snomed_search._get_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM snomed_fts")
                    desc_count = cursor.fetchone()[0]
                    return TerminologyInfo(
                        total_concepts=desc_count,
                        file_name=f"SNOMED CT SQLite ({desc_count} descriptions)",
                        loaded=True,
                    )
                except Exception:
                    pass
            else:
                desc_count = len(getattr(self._snomed_search, "descriptions", []))
                return TerminologyInfo(
                    total_concepts=desc_count,
                    file_name=f"SNOMED CT RF2 ({desc_count} descriptions)",
                    loaded=True,
                )
        return self._tsv_index.info()

    def load_snomed(self, rf2_dir: Path) -> int:
        """
        Load SNOMED CT from RF2 files.

        Tries in order:
        1. SQLite database (if path provided and exists)
        2. SQLite database (build from RF2 if path provided)
        3. In-memory search (from RF2)
        """
        # Try SQLite first if path provided
        if self._db_path:
            try:
                from textractor.terminology.snomed_sqlite import SNOMEDSearchSQLite

                self._snomed_search = SNOMEDSearchSQLite(self._db_path)

                # Check if database is already indexed
                if self._snomed_search.is_indexed():
                    logger.info("Using existing SNOMED SQLite database at %s", self._db_path)
                    self._snomed_loaded = True
                    self._snomed_path = str(rf2_dir)
                    self._using_sqlite = True

                    # Get count for return value
                    conn = self._snomed_search._get_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM snomed_fts")
                    desc_count = cursor.fetchone()[0]
                    return desc_count
                else:
                    # Build index from RF2 files
                    logger.info("Building SNOMED SQLite index from %s", rf2_dir)
                    desc_count = self._snomed_search.build_index(rf2_dir)
                    self._snomed_loaded = True
                    self._snomed_path = str(rf2_dir)
                    self._using_sqlite = True
                    logger.info("Built SNOMED SQLite index with %d descriptions", desc_count)
                    return desc_count

            except Exception as exc:
                logger.warning("Failed to use SQLite, falling back to in-memory: %s", exc)
                # Fall through to in-memory

        # Fall back to in-memory SNOMED search
        try:
            from textractor.terminology.snomed import SNOMEDSearch

            logger.info("Loading SNOMED into memory from %s", rf2_dir)
            self._snomed_search = SNOMEDSearch()
            self._snomed_search.load(str(rf2_dir))
            self._snomed_loaded = True
            self._snomed_path = str(rf2_dir)
            self._using_sqlite = False

            desc_count = len(self._snomed_search.descriptions)
            logger.info("Loaded SNOMED CT (in-memory) with %d active descriptions", desc_count)
            return desc_count

        except ImportError as exc:
            logger.warning("SNOMED search not available: %s", exc)
            return 0
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
