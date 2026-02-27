from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..annotation_store import SQLiteAnnotationStore
from ..dependencies import get_annotation_store, get_store
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
    doc_id: str,
    annotator: str = "default",
    doc_store: DocumentStore = Depends(get_store),
    ann_store: SQLiteAnnotationStore = Depends(get_annotation_store),
) -> AnnotationFile:
    """Get the current annotations for a document."""
    if not doc_store.document_exists(doc_id):
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")

    annotations = ann_store.get_annotations(doc_id, annotator=annotator)
    if annotations is None:
        # Return empty annotations if none exist
        return AnnotationFile(doc_id=doc_id, completed=False)
    return annotations


@router.put("/{doc_id}/annotations", response_model=AnnotationFile)
def save_annotations(
    doc_id: str,
    ann: AnnotationFile,
    annotator: str = "default",
    doc_store: DocumentStore = Depends(get_store),
    ann_store: SQLiteAnnotationStore = Depends(get_annotation_store),
) -> AnnotationFile:
    """Save annotations as a new version."""
    import logging
    logger = logging.getLogger(__name__)

    if not doc_store.document_exists(doc_id):
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")
    if ann.doc_id != doc_id:
        logger.error(f"doc_id mismatch: URL={doc_id}, body={ann.doc_id}")
        raise HTTPException(
            status_code=400, detail="doc_id in body does not match URL parameter"
        )

    # Prevent modifications to completed documents (except unchecking completed status)
    if ann_store.is_completed(doc_id, annotator=annotator) and ann.completed:
        raise HTTPException(
            status_code=403,
            detail="Cannot modify annotations for a completed document. Uncheck 'Completed' first to make changes.",
        )

    logger.info(f"Saving annotations for {doc_id}: {len(ann.spans)} spans, {len(ann.reasoning_steps)} steps, {len(ann.document_annotations)} annotations")
    _validate_referential_integrity(ann)
    ann_store.save_annotations(doc_id, ann, annotator=annotator, source="human")
    return ann


@router.get("/{doc_id}/annotations/history")
def get_annotation_history(
    doc_id: str,
    annotator: str = "default",
    doc_store: DocumentStore = Depends(get_store),
    ann_store: SQLiteAnnotationStore = Depends(get_annotation_store),
) -> list[dict]:
    """Get version history for a document's annotations."""
    if not doc_store.document_exists(doc_id):
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")

    return ann_store.get_history(doc_id, annotator=annotator)


@router.post("/{doc_id}/annotations/revert/{version}", response_model=AnnotationFile)
def revert_to_version(
    doc_id: str,
    version: int,
    annotator: str = "default",
    doc_store: DocumentStore = Depends(get_store),
    ann_store: SQLiteAnnotationStore = Depends(get_annotation_store),
) -> AnnotationFile:
    """Revert to a specific version of annotations."""
    if not doc_store.document_exists(doc_id):
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")

    try:
        return ann_store.revert_to_version(doc_id, version, annotator=annotator)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
