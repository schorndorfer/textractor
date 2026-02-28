"""Health check endpoint for infrastructure monitoring."""
from __future__ import annotations

import logging
import os
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from .. import dependencies

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded"]
    snomed_available: bool
    doc_root_accessible: bool
    document_count: int
    db_accessible: bool


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """
    Return application health status.

    Always returns HTTP 200. Use the `status` field to distinguish
    healthy from degraded states. Intended for Docker HEALTHCHECK,
    load balancers, and monitoring systems.
    """
    _terminology = dependencies._terminology
    _store = dependencies._store
    _annotation_store = dependencies._annotation_store

    snomed_available = _terminology is not None and _terminology.is_loaded

    doc_root_accessible = False
    document_count = 0
    if _store is not None:
        try:
            doc_root_accessible = os.access(_store.root, os.R_OK)
            document_count = len(_store.list_documents())
        except Exception:
            logger.exception("Health check: error accessing document store")

    db_accessible = False
    if _annotation_store is not None:
        try:
            import sqlite3
            with sqlite3.connect(_annotation_store.db_path, timeout=2.0) as conn:
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
