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


def init_terminology(
    snomed_dir: Optional[Path] = None,
    icd10cm_file: Optional[Path] = None,
    icd10cm_db_path: Optional[Path] = None,
) -> None:
    """
    Initialize terminology indices (SNOMED CT and/or ICD-10-CM).

    Args:
        snomed_dir: Optional path to SNOMED CT RF2 directory
        icd10cm_file: Optional path to CMS ICD-10-CM flat file
        icd10cm_db_path: Optional path for ICD-10-CM SQLite database.
            Defaults to icd10cm_file.parent/icd10cm.db when not provided.
            Override in Docker to place the DB in a writable volume.
    """
    global _terminology

    db_path = None
    if snomed_dir and snomed_dir.exists():
        db_path = snomed_dir.parent / "snomed.db"

    resolved_icd10cm_db_path = None
    if icd10cm_file and icd10cm_file.exists():
        resolved_icd10cm_db_path = icd10cm_db_path or (icd10cm_file.parent / "icd10cm.db")

    _terminology = EnhancedTerminologyIndex(
        db_path=db_path,
        icd10cm_db_path=resolved_icd10cm_db_path,
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


def get_store_optional() -> Optional[DocumentStore]:
    """Get the document store if initialized, None otherwise."""
    return _store


def get_terminology_optional() -> Optional[EnhancedTerminologyIndex]:
    """Get the terminology index if initialized, None otherwise."""
    return _terminology


def get_annotation_store_optional() -> Optional[SQLiteAnnotationStore]:
    """Get the annotation store if initialized, None otherwise."""
    return _annotation_store
