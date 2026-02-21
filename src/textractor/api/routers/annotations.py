from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_store
from ..models import AnnotationFile
from ..storage import DocumentStore

router = APIRouter(prefix="/api/documents", tags=["annotations"])


@router.get("/{doc_id}/annotations", response_model=AnnotationFile)
def get_annotations(
    doc_id: str, store: DocumentStore = Depends(get_store)
) -> AnnotationFile:
    if not store.document_exists(doc_id):
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")
    return store.get_annotations(doc_id)


@router.put("/{doc_id}/annotations", response_model=AnnotationFile)
def save_annotations(
    doc_id: str,
    ann: AnnotationFile,
    store: DocumentStore = Depends(get_store),
) -> AnnotationFile:
    if not store.document_exists(doc_id):
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")
    if ann.doc_id != doc_id:
        raise HTTPException(
            status_code=400, detail="doc_id in body does not match URL parameter"
        )

    span_ids = {s.id for s in ann.spans}
    step_ids = {s.id for s in ann.reasoning_steps}

    for step in ann.reasoning_steps:
        missing = set(step.span_ids) - span_ids
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"Reasoning step '{step.id}' references unknown span IDs: {sorted(missing)}",
            )

    for doc_ann in ann.document_annotations:
        missing_spans = set(doc_ann.evidence_span_ids) - span_ids
        missing_steps = set(doc_ann.reasoning_step_ids) - step_ids
        if missing_spans:
            raise HTTPException(
                status_code=422,
                detail=f"Annotation '{doc_ann.id}' references unknown span IDs: {sorted(missing_spans)}",
            )
        if missing_steps:
            raise HTTPException(
                status_code=422,
                detail=f"Annotation '{doc_ann.id}' references unknown step IDs: {sorted(missing_steps)}",
            )

    store.save_annotations(ann)
    return ann
