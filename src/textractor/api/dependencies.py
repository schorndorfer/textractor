from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .annotation_store import SQLiteAnnotationStore
from .enhanced_terminology import EnhancedTerminologyIndex
from .storage import DocumentStore

logger = logging.getLogger(__name__)

_store: Optional[DocumentStore] = None
_terminology: Optional[EnhancedTerminologyIndex] = None
_annotation_store: Optional[SQLiteAnnotationStore] = None


def init_store(root: Path) -> None:
    global _store
    _store = DocumentStore(root)


def init_terminology(snomed_dir: Optional[Path] = None) -> None:
    """
    Initialize SNOMED CT terminology index.

    Args:
        snomed_dir: Optional path to SNOMED CT RF2 directory (data/terminology/SnomedCT)
    """
    global _terminology

    # Use SQLite database if SNOMED directory exists
    db_path = None
    if snomed_dir and snomed_dir.exists():
        db_path = snomed_dir.parent / "snomed.db"

    _terminology = EnhancedTerminologyIndex(db_path=db_path)

    # Load SNOMED CT if directory exists
    if snomed_dir and snomed_dir.exists():
        count = _terminology.load_snomed(snomed_dir)
        if count > 0:
            logger.info("Loaded SNOMED CT with %d active descriptions", count)
        else:
            logger.warning("Failed to load SNOMED CT from %s", snomed_dir)
    else:
        logger.info("No SNOMED directory provided - terminology search will be empty")


def get_store() -> DocumentStore:
    if _store is None:
        raise RuntimeError("Document store not initialized")
    return _store


def get_terminology() -> EnhancedTerminologyIndex:
    if _terminology is None:
        raise RuntimeError("Terminology index not initialized")
    return _terminology


def init_annotation_store(db_path: Path) -> None:
    """Initialize SQLite annotation store."""
    global _annotation_store
    _annotation_store = SQLiteAnnotationStore(db_path)
    logger.info("Initialized annotation store at %s", db_path)


def get_annotation_store() -> SQLiteAnnotationStore:
    """Get the annotation store singleton."""
    if _annotation_store is None:
        raise RuntimeError("Annotation store not initialized")
    return _annotation_store
