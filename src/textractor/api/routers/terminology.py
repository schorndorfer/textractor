from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from ..dependencies import get_terminology
from ..models import TerminologyConcept, TerminologyInfo
from ..terminology import TerminologyIndex

router = APIRouter(prefix="/api/terminology", tags=["terminology"])


@router.get("/search", response_model=list[TerminologyConcept])
def search_concepts(
    q: str = Query(default="", description="Substring search query"),
    limit: int = Query(default=20, ge=1, le=200),
    index: TerminologyIndex = Depends(get_terminology),
) -> list[TerminologyConcept]:
    return index.search(q, limit=limit)


@router.get("/info", response_model=TerminologyInfo)
def terminology_info(index: TerminologyIndex = Depends(get_terminology)) -> TerminologyInfo:
    return index.info()


@router.post("/upload", response_model=TerminologyInfo)
async def upload_terminology(
    file: UploadFile = File(...),
    index: TerminologyIndex = Depends(get_terminology),
) -> TerminologyInfo:
    if not (file.filename or "").endswith(".tsv"):
        raise HTTPException(status_code=400, detail="Only .tsv files are accepted")

    content = await file.read()
    try:
        index.load_from_bytes(content, file.filename or "uploaded.tsv")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return index.info()
