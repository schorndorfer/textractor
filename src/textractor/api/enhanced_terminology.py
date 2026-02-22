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
    Terminology search that uses SNOMED CT RF2 files when available,
    falling back to TSV-based simple search.
    """

    def __init__(self) -> None:
        self._snomed_search: Optional[object] = None  # SNOMEDSearch instance
        self._tsv_index = TerminologyIndex()
        self._snomed_loaded = False
        self._snomed_path: Optional[str] = None

    @property
    def is_loaded(self) -> bool:
        return self._snomed_loaded or self._tsv_index.is_loaded

    def info(self) -> TerminologyInfo:
        if self._snomed_loaded and self._snomed_search:
            # Get description count from SNOMED
            desc_count = len(getattr(self._snomed_search, "descriptions", []))
            return TerminologyInfo(
                total_concepts=desc_count,
                file_name=f"SNOMED CT RF2 ({desc_count} descriptions)",
                loaded=True,
            )
        return self._tsv_index.info()

    def load_snomed(self, rf2_dir: Path) -> int:
        """Load SNOMED CT RF2 files from directory."""
        try:
            # Import here to avoid dependency if SNOMED not used
            from textractor.terminology.snomed import SNOMEDSearch

            self._snomed_search = SNOMEDSearch()
            self._snomed_search.load(str(rf2_dir))
            self._snomed_loaded = True
            self._snomed_path = str(rf2_dir)

            desc_count = len(self._snomed_search.descriptions)
            logger.info("Loaded SNOMED CT with %d active descriptions", desc_count)
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
