"""Tests for shared export utilities."""
import io
import json
import tempfile
import zipfile
from pathlib import Path

import pytest

from textractor.api.export_utils import create_export_zip
from textractor.api.storage import DocumentStore
from textractor.api.annotation_store import SQLiteAnnotationStore
from textractor.api.models import Document, DocumentSummary, AnnotationFile, Span


@pytest.fixture
def test_stores():
    """Create test document and annotation stores."""
    with tempfile.TemporaryDirectory() as tmpdir:
        doc_root = Path(tmpdir)

        # Create test documents
        doc1 = doc_root / "doc_001.json"
        doc1.write_text(json.dumps({
            "id": "doc_001",
            "text": "First document",
            "metadata": {"project": "test-project"}
        }))

        doc2 = doc_root / "doc_002.json"
        doc2.write_text(json.dumps({
            "id": "doc_002",
            "text": "Second document",
            "metadata": {"project": "test-project"}
        }))

        # Initialize stores
        doc_store = DocumentStore(doc_root)
        ann_store = SQLiteAnnotationStore(doc_root / "test.db")

        # Add annotations for doc_001
        ann_store.save_annotations(
            doc_id="doc_001",
            annotations=AnnotationFile(
                doc_id="doc_001",
                spans=[Span(id="span_1", start=0, end=5, text="First")],
                reasoning_steps=[],
                document_annotations=[],
                completed=False,
            ),
            annotator="default",
            source="human",
        )

        yield doc_store, ann_store


def test_create_export_zip_with_documents_and_annotations(test_stores):
    """Test that create_export_zip generates a valid ZIP with docs and annotations."""
    doc_store, ann_store = test_stores

    # Get documents to export
    all_docs = doc_store.list_documents()
    docs_to_export = [d for d in all_docs if d.metadata.get("project") == "test-project"]

    # Create ZIP
    zip_bytes = create_export_zip(docs_to_export, doc_store, ann_store, annotator="default")

    # Verify it's valid ZIP bytes
    assert isinstance(zip_bytes, bytes)
    assert len(zip_bytes) > 0

    # Verify ZIP contents
    zip_data = io.BytesIO(zip_bytes)
    with zipfile.ZipFile(zip_data, 'r') as zf:
        files = zf.namelist()

        # Should contain both documents
        assert "doc_001.json" in files
        assert "doc_002.json" in files

        # Should contain annotations for doc_001
        assert "doc_001.ann.json" in files

        # Verify document content
        doc1_content = json.loads(zf.read("doc_001.json"))
        assert doc1_content["id"] == "doc_001"

        # Verify annotation content
        ann1_content = json.loads(zf.read("doc_001.ann.json"))
        assert ann1_content["doc_id"] == "doc_001"
        assert len(ann1_content["spans"]) == 1


def test_create_export_zip_empty_list(test_stores):
    """Test that create_export_zip handles empty document list."""
    doc_store, ann_store = test_stores

    # Create ZIP with no documents
    zip_bytes = create_export_zip([], doc_store, ann_store)

    # Should still be valid ZIP
    assert isinstance(zip_bytes, bytes)

    zip_data = io.BytesIO(zip_bytes)
    with zipfile.ZipFile(zip_data, 'r') as zf:
        assert len(zf.namelist()) == 0
