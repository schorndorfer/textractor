from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .enhanced_terminology import EnhancedTerminologyIndex
from .storage import DocumentStore

logger = logging.getLogger(__name__)

_store: Optional[DocumentStore] = None
_terminology: Optional[EnhancedTerminologyIndex] = None


def init_store(root: Path) -> None:
    global _store
    _store = DocumentStore(root)


def init_terminology(tsv_path: Optional[Path], snomed_dir: Optional[Path] = None) -> None:
    """
    Initialize terminology index.

    Args:
        tsv_path: Optional path to TSV terminology file (legacy)
        snomed_dir: Optional path to SNOMED CT RF2 directory (data/terminology/SnomedCT)
    """
    global _terminology
    _terminology = EnhancedTerminologyIndex()

    # Try to load SNOMED CT first (if directory exists)
    if snomed_dir and snomed_dir.exists():
        count = _terminology.load_snomed(snomed_dir)
        if count > 0:
            logger.info("Loaded SNOMED CT with %d active descriptions", count)
            return  # SNOMED loaded successfully, don't load TSV

    # Fall back to TSV if provided
    if tsv_path and tsv_path.exists():
        count = _terminology.load_from_path(tsv_path)
        logger.info("Loaded %d concepts from TSV: %s", count, tsv_path)
    else:
        logger.info("No terminology loaded - search will be empty")


def get_store() -> DocumentStore:
    if _store is None:
        raise RuntimeError("Document store not initialized")
    return _store


def get_terminology() -> EnhancedTerminologyIndex:
    if _terminology is None:
        raise RuntimeError("Terminology index not initialized")
    return _terminology
