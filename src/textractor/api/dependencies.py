from __future__ import annotations

from pathlib import Path
from typing import Optional

from .storage import DocumentStore
from .terminology import TerminologyIndex

_store: Optional[DocumentStore] = None
_terminology: Optional[TerminologyIndex] = None


def init_store(root: Path) -> None:
    global _store
    _store = DocumentStore(root)


def init_terminology(path: Optional[Path]) -> None:
    global _terminology
    _terminology = TerminologyIndex()
    if path and path.exists():
        count = _terminology.load_from_path(path)
        import logging
        logging.getLogger(__name__).info("Loaded %d concepts from %s", count, path)


def get_store() -> DocumentStore:
    if _store is None:
        raise RuntimeError("Document store not initialized")
    return _store


def get_terminology() -> TerminologyIndex:
    if _terminology is None:
        raise RuntimeError("Terminology index not initialized")
    return _terminology
