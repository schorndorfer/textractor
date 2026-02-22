from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..dependencies import get_terminology
from ..enhanced_terminology import EnhancedTerminologyIndex
from ..models import TerminologyConcept, TerminologyInfo

router = APIRouter(prefix="/api/terminology", tags=["terminology"])


@router.get("/search", response_model=list[TerminologyConcept])
def search_concepts(
    q: str = Query(default="", description="SNOMED CT search query"),
    limit: int = Query(default=20, ge=1, le=200),
    index: EnhancedTerminologyIndex = Depends(get_terminology),
) -> list[TerminologyConcept]:
    """Search SNOMED CT terminology using full-text search."""
    return index.search(q, limit=limit)


@router.get("/info", response_model=TerminologyInfo)
def terminology_info(index: EnhancedTerminologyIndex = Depends(get_terminology)) -> TerminologyInfo:
    """Get information about the loaded terminology."""
    return index.info()
