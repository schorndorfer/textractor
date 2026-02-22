from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_store, get_terminology
from ..enhanced_terminology import EnhancedTerminologyIndex
from ..llm import extract_medical_terms, generate_annotations_raw, validate_and_convert_annotations
from ..models import AnnotationFile
from ..storage import DocumentStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["preannotate"])


@router.post("/{doc_id}/preannotate", response_model=AnnotationFile)
def preannotate_document(
    doc_id: str,
    store: DocumentStore = Depends(get_store),
    terminology: EnhancedTerminologyIndex = Depends(get_terminology),
) -> AnnotationFile:
    """
    Generate AI annotations for a document using Claude AI.

    This endpoint:
    1. Extracts medical terms from the document
    2. Searches SNOMED for relevant concepts
    3. Generates structured annotations with validated SNOMED codes
    4. Returns annotations with source='model' for user review

    The annotations are NOT automatically saved - the frontend handles review
    and saving workflow.

    Args:
        doc_id: Document ID to annotate
        store: Document storage
        terminology: SNOMED terminology index

    Returns:
        AnnotationFile with generated annotations

    Raises:
        HTTPException 404: Document not found
        HTTPException 403: Document is locked/completed
        HTTPException 500: API key not configured
        HTTPException 502: LLM API error
    """
    # Check API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY environment variable not configured",
        )

    # Check document exists
    if not store.document_exists(doc_id):
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")

    # Check document isn't locked
    existing_annotations = store.get_annotations(doc_id)
    if existing_annotations.completed:
        raise HTTPException(
            status_code=403,
            detail="Cannot pre-annotate a completed document",
        )

    # Get document text
    doc = store.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")

    model = os.environ.get("TEXTRACTOR_LLM_MODEL", "claude-sonnet-4-5")

    try:
        # Stage 1: Extract medical terms
        logger.info(f"Extracting medical terms from document '{doc_id}'")
        terms = extract_medical_terms(doc.text, api_key=api_key, model=model)
        logger.info(f"Extracted {len(terms)} terms: {terms}")

        # Search SNOMED for each term
        snomed_candidates = []
        for term in terms:
            results = terminology.search(term, limit=5)
            snomed_candidates.extend(results)
            logger.info(f"SNOMED search for '{term}': {len(results)} results")

        if not snomed_candidates:
            logger.warning("No SNOMED candidates found for any term")

        # Stage 2: Generate annotations
        logger.info(f"Generating annotations with {len(snomed_candidates)} SNOMED candidates")
        raw_annotations = generate_annotations_raw(
            doc.text,
            snomed_candidates,
            api_key=api_key,
            model=model,
        )

        # Validate and convert
        threshold = int(os.environ.get("TEXTRACTOR_FUZZY_THRESHOLD", "90"))
        annotation_file = validate_and_convert_annotations(
            raw_annotations,
            doc.text,
            doc_id,
            threshold=threshold,
        )

        logger.info(
            f"Pre-annotation complete: {len(annotation_file.spans)} spans, "
            f"{len(annotation_file.reasoning_steps)} steps, "
            f"{len(annotation_file.document_annotations)} annotations"
        )

        return annotation_file

    except ValueError as e:
        logger.error(f"LLM validation error: {e}")
        raise HTTPException(status_code=502, detail=f"LLM response error: {str(e)}")
    except Exception as e:
        logger.error(f"Pre-annotation error: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Pre-annotation failed: {str(e)}")
