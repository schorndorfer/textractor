from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ..dependencies import get_store
from ..models import Document, DocumentSummary
from ..storage import DocumentStore

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("", response_model=list[DocumentSummary])
def list_documents(store: DocumentStore = Depends(get_store)) -> list[DocumentSummary]:
    return store.list_documents()


@router.post("/upload", response_model=DocumentSummary)
async def upload_document(
    file: UploadFile = File(...),
    store: DocumentStore = Depends(get_store),
) -> DocumentSummary:
    if not (file.filename or "").endswith(".json"):
        raise HTTPException(status_code=400, detail="Only .json files are accepted")

    content = await file.read()
    try:
        data = json.loads(content)
        doc = Document.model_validate(data)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid document JSON: {exc}") from exc

    if store.document_exists(doc.id):
        raise HTTPException(status_code=409, detail=f"Document '{doc.id}' already exists")

    store.save_document(doc)
    return DocumentSummary(
        id=doc.id,
        metadata=doc.metadata,
        is_annotated=False,
        text_preview=doc.text[:200],
    )


@router.get("/{doc_id}", response_model=Document)
def get_document(doc_id: str, store: DocumentStore = Depends(get_store)) -> Document:
    doc = store.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")
    return doc
