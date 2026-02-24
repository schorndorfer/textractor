"""Shared utilities for exporting documents and annotations."""
from __future__ import annotations

import io
import logging
import zipfile

from .annotation_store import SQLiteAnnotationStore
from .models import DocumentSummary
from .storage import DocumentStore

logger = logging.getLogger(__name__)


def create_export_zip(
    docs_to_export: list[DocumentSummary],
    doc_store: DocumentStore,
    ann_store: SQLiteAnnotationStore,
    annotator: str = "default",
) -> bytes:
    """Create ZIP file containing documents and annotations.

    Args:
        docs_to_export: List of document summaries to export
        doc_store: Document store instance
        ann_store: Annotation store instance
        annotator: Annotator name for annotations (default: "default")

    Returns:
        ZIP file as bytes
    """
    # Create ZIP in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for doc_summary in docs_to_export:
            # Add document JSON
            doc = doc_store.get_document(doc_summary.id)
            if doc:
                doc_json = doc.model_dump_json(indent=2)
                zf.writestr(f"{doc.id}.json", doc_json)
            else:
                logger.warning(f"Failed to load document {doc_summary.id} for export")

            # Add annotations JSON if they exist
            annotations = ann_store.get_annotations(doc_summary.id, annotator=annotator)
            if annotations:
                ann_json = annotations.model_dump_json(indent=2)
                zf.writestr(f"{doc_summary.id}.ann.json", ann_json)

    # Return bytes
    zip_buffer.seek(0)
    return zip_buffer.read()
