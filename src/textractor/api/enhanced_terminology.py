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
        db_path: Optional[Path] = None,
        icd10cm_db_path: Optional[Path] = None,
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
