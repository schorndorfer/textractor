"""Tests for project export functionality."""
import io
import json
import tempfile
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from textractor.api.main import create_app
from textractor.api.dependencies import init_annotation_store, init_store, init_terminology
from textractor.api.models import Document, AnnotationFile, Span


@pytest.fixture
def client_with_project():
    """Create a test client with a project containing documents and annotations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        doc_root = Path(tmpdir)

        # Create documents in test-project
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

        # Create document in different project
        doc3 = doc_root / "doc_003.json"
        doc3.write_text(json.dumps({
            "id": "doc_003",
            "text": "Other project",
            "metadata": {"project": "other-project"}
        }))

        # Initialize app
        init_store(doc_root)
        init_annotation_store(doc_root / "test.db")
        init_terminology(snomed_dir=None)

        # Add annotations for doc_001
        from textractor.api.dependencies import get_annotation_store
        ann_store = get_annotation_store()
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

        app = create_app()
        yield TestClient(app)


def test_export_project_returns_zip(client_with_project):
    """Test that exporting a project returns a ZIP file."""
    response = client_with_project.get("/api/documents/export?project=test-project")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
    assert "test-project" in response.headers["content-disposition"]


def test_export_project_contains_documents(client_with_project):
    """Test that exported ZIP contains document JSON files."""
    response = client_with_project.get("/api/documents/export?project=test-project")

    zip_data = io.BytesIO(response.content)
    with zipfile.ZipFile(zip_data, 'r') as zf:
        files = zf.namelist()
        assert "doc_001.json" in files
        assert "doc_002.json" in files
        assert "doc_003.json" not in files  # Different project

        # Verify document content
        doc1_content = json.loads(zf.read("doc_001.json"))
        assert doc1_content["id"] == "doc_001"
        assert doc1_content["text"] == "First document"


def test_export_project_contains_annotations(client_with_project):
    """Test that exported ZIP contains annotation JSON files."""
    response = client_with_project.get("/api/documents/export?project=test-project")

    zip_data = io.BytesIO(response.content)
    with zipfile.ZipFile(zip_data, 'r') as zf:
        files = zf.namelist()
        assert "doc_001.ann.json" in files

        # Verify annotation content
        ann_content = json.loads(zf.read("doc_001.ann.json"))
        assert ann_content["doc_id"] == "doc_001"
        assert len(ann_content["spans"]) == 1
        assert ann_content["spans"][0]["text"] == "First"


def test_export_all_documents(client_with_project):
    """Test exporting all documents when no project specified."""
    response = client_with_project.get("/api/documents/export")

    assert response.status_code == 200

    zip_data = io.BytesIO(response.content)
    with zipfile.ZipFile(zip_data, 'r') as zf:
        files = zf.namelist()
        assert "doc_001.json" in files
        assert "doc_002.json" in files
        assert "doc_003.json" in files


def test_export_nonexistent_project(client_with_project):
    """Test exporting a project that doesn't exist."""
    response = client_with_project.get("/api/documents/export?project=nonexistent")

    assert response.status_code == 200  # Empty ZIP is valid

    zip_data = io.BytesIO(response.content)
    with zipfile.ZipFile(zip_data, 'r') as zf:
        assert len(zf.namelist()) == 0
