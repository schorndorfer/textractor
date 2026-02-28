"""Health check endpoint for infrastructure monitoring."""
from __future__ import annotations

import logging
import os
import sqlite3
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..annotation_store import SQLiteAnnotationStore
from ..dependencies import get_annotation_store_optional, get_store_optional, get_terminology_optional
from ..enhanced_terminology import EnhancedTerminologyIndex
from ..storage import DocumentStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded"]
    snomed_available: bool
    doc_root_accessible: bool
    document_count: int
    db_accessible: bool


@router.get("/health", response_model=HealthResponse)
def health_check(
    store: Optional[DocumentStore] = Depends(get_store_optional),
    terminology: Optional[EnhancedTerminologyIndex] = Depends(get_terminology_optional),
    ann_store: Optional[SQLiteAnnotationStore] = Depends(get_annotation_store_optional),
) -> HealthResponse:
    """
    Return application health status.

    Always returns HTTP 200. Use the `status` field to distinguish
    healthy from degraded states. Intended for Docker HEALTHCHECK,
    load balancers, and monitoring systems.
    """
    snomed_available = terminology is not None and terminology.is_loaded

    doc_root_accessible = False
    document_count = 0
    if store is not None:
        try:
            doc_root_accessible = os.access(store.root, os.R_OK)
            document_count = len(store.list_documents())
        except Exception:
            logger.exception("Health check: error accessing document store")

    db_accessible = False
    if ann_store is not None:
        try:
            with sqlite3.connect(ann_store.db_path, timeout=2.0) as conn:
                conn.execute("SELECT 1")
            db_accessible = True
        except Exception:
            logger.exception("Health check: error accessing SQLite database")

    all_ok = snomed_available and doc_root_accessible and db_accessible
    status: Literal["healthy", "degraded"] = "healthy" if all_ok else "degraded"

    return HealthResponse(
        status=status,
        snomed_available=snomed_available,
        doc_root_accessible=doc_root_accessible,
        document_count=document_count,
        db_accessible=db_accessible,
    )
