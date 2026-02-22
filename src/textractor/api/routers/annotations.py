from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_store
from ..models import AnnotationFile
from ..storage import DocumentStore

router = APIRouter(prefix="/api/documents", tags=["annotations"])


def _validate_referential_integrity(ann: AnnotationFile) -> None:
    """
    Validate that all ID references in the annotation file are valid.

    Raises HTTPException if validation fails.
    """
    span_ids = {s.id for s in ann.spans}
    step_ids = {s.id for s in ann.reasoning_steps}

    # Validate reasoning steps reference valid spans
    for step in ann.reasoning_steps:
        missing = set(step.span_ids) - span_ids
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"Reasoning step '{step.id}' references unknown span IDs: {sorted(missing)}",
            )

    # Validate document annotations reference valid spans and steps
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

    # Prevent modifications to completed documents (except unchecking completed status)
    existing = store.get_annotations(doc_id)
    if existing.completed and ann.completed:
        raise HTTPException(
            status_code=403,
            detail="Cannot modify annotations for a completed document. Uncheck 'Completed' first to make changes.",
        )

    _validate_referential_integrity(ann)
    store.save_annotations(ann)
    return ann
