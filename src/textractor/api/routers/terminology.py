from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies import get_terminology
from ..enhanced_terminology import EnhancedTerminologyIndex
from ..models import TerminologyConcept, TerminologyInfo

router = APIRouter(prefix="/api/terminology", tags=["terminology"])

VALID_SYSTEMS = {"SNOMED-CT", "ICD-10-CM"}


@router.get("/search", response_model=list[TerminologyConcept])
def search_concepts(
    q: str = Query(default="", description="Terminology search query"),
    limit: int = Query(default=20, ge=1, le=200),
    system: Optional[str] = Query(
        default=None,
        description="Terminology system: SNOMED-CT or ICD-10-CM",
    ),
    index: EnhancedTerminologyIndex = Depends(get_terminology),
) -> list[TerminologyConcept]:
    """Search terminology using full-text search."""
    if system is not None and system not in VALID_SYSTEMS:
        raise HTTPException(
            status_code=422,
            detail=f"system must be one of: {sorted(VALID_SYSTEMS)}",
        )
    return index.search(q, limit=limit, system=system)


@router.get("/info", response_model=TerminologyInfo)
def terminology_info(
    index: EnhancedTerminologyIndex = Depends(get_terminology),
) -> TerminologyInfo:
    """Get information about all loaded terminology systems."""
    return index.info()
