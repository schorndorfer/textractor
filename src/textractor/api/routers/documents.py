from __future__ import annotations

import io
import json
from urllib.parse import quote

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..annotation_store import SQLiteAnnotationStore
from ..dependencies import get_annotation_store, get_store
from ..export_utils import create_export_zip
from ..models import Document, DocumentSummary
from ..storage import DocumentStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("", response_model=list[DocumentSummary])
def list_documents(
    doc_store: DocumentStore = Depends(get_store),
    ann_store: SQLiteAnnotationStore = Depends(get_annotation_store),
    annotator: str = "default",
) -> list[DocumentSummary]:
    """List all documents with annotation status from SQLite."""
    documents = doc_store.list_documents()

    # Update annotation status from SQLite (ignoring file-based status)
    for doc in documents:
        doc.is_annotated = ann_store.is_annotated(doc.id, annotator=annotator)
        doc.is_completed = ann_store.is_completed(doc.id, annotator=annotator)

    return documents


@router.post("/upload", response_model=list[DocumentSummary])
async def upload_documents(
    files: list[UploadFile] = File(...),
    annotator: str = "default",
    doc_store: DocumentStore = Depends(get_store),
    ann_store: SQLiteAnnotationStore = Depends(get_annotation_store),
) -> list[DocumentSummary]:
    """Upload one or more document JSON files."""
    summaries: list[DocumentSummary] = []
    errors: list[str] = []

    for file in files:
        if not (file.filename or "").endswith(".json"):
            errors.append(f"{file.filename}: Only .json files are accepted")
            continue

        try:
            content = await file.read()
            data = json.loads(content)
            doc = Document.model_validate(data)

            if doc_store.document_exists(doc.id):
                errors.append(f"{file.filename}: Document '{doc.id}' already exists")
                continue

            doc_store.save_document(doc)

            # Check annotation status from SQLite
            is_annotated = ann_store.is_annotated(doc.id, annotator=annotator)
            is_completed = ann_store.is_completed(doc.id, annotator=annotator)

            summaries.append(
                DocumentSummary(
                    id=doc.id,
                    metadata=doc.metadata,
                    is_annotated=is_annotated,
                    is_completed=is_completed,
                    text_preview=doc.text[:200],
                )
            )
        except Exception as exc:
            errors.append(f"{file.filename}: Invalid document JSON: {exc}")

    if errors and not summaries:
        # All uploads failed
        raise HTTPException(status_code=422, detail="; ".join(errors))

    # Return successfully uploaded documents (with warnings in logs if partial failure)
    if errors:
        logger.warning("Partial upload failure: %s", "; ".join(errors))

    return summaries


@router.get("/export")
def export_project(
    project: str | None = None,
    annotator: str = "default",
    doc_store: DocumentStore = Depends(get_store),
    ann_store: SQLiteAnnotationStore = Depends(get_annotation_store),
):
    """Export documents and annotations as a ZIP file.

    Args:
        project: Project name to export. If None, exports all documents.
        annotator: Annotator name for annotations (default: "default")

    Returns:
        ZIP file containing document JSON files and annotation JSON files.
    """
    # Get all documents
    all_docs = doc_store.list_documents()

    # Filter by project if specified
    if project is not None:
        docs_to_export = [
            d for d in all_docs if d.metadata.get("project") == project
        ]
    else:
        docs_to_export = all_docs

    # Create ZIP using shared utility
    zip_bytes = create_export_zip(docs_to_export, doc_store, ann_store, annotator)

    # Prepare response
    zip_buffer = io.BytesIO(zip_bytes)
    filename_safe = quote(project or "all-documents", safe="")
    filename = f"{filename_safe}.zip"

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{doc_id}", response_model=Document)
def get_document(doc_id: str, store: DocumentStore = Depends(get_store)) -> Document:
    doc = store.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")
    return doc


class UpdateDocumentMetadata(BaseModel):
    metadata: dict


@router.patch("/{doc_id}/metadata", response_model=Document)
def update_document_metadata(
    doc_id: str,
    update: UpdateDocumentMetadata,
    store: DocumentStore = Depends(get_store),
) -> Document:
    """Update document metadata fields."""
    doc = store.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")

    # Update metadata
    doc.metadata.update(update.metadata)
    store.save_document(doc)
    return doc


@router.delete("/{doc_id}")
def delete_document(
    doc_id: str,
    doc_store: DocumentStore = Depends(get_store),
    ann_store: SQLiteAnnotationStore = Depends(get_annotation_store),
) -> dict:
    """Delete a document and its annotations (from both filesystem and SQLite)."""
    doc_path = doc_store._doc_path(doc_id)

    if not doc_path.exists():
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")

    # Delete document file
    doc_path.unlink()

    # Delete annotations from SQLite (all annotators)
    ann_store.delete_annotations(doc_id)

    # Also delete legacy .ann.json file if it exists
    ann_path = doc_store._ann_path(doc_id)
    if ann_path.exists():
        ann_path.unlink()

    return {"status": "deleted", "doc_id": doc_id}
