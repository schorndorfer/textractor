"""Tests for CLI export command."""

import json
import os
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from textractor.api.annotation_store import SQLiteAnnotationStore
from textractor.api.models import AnnotationFile, Document, DocumentSummary, Span
from textractor.api.storage import DocumentStore
from textractor.cli.export import export_project, main


@pytest.fixture
def test_project_setup():
    """Set up test project with documents and annotations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        doc_root = Path(tmpdir)
        db_path = doc_root / "test.db"

        # Create test documents
        doc1 = doc_root / "doc_001.json"
        doc1.write_text(
            json.dumps(
                {"id": "doc_001", "text": "First document", "metadata": {"project": "test-project"}}
            )
        )

        doc2 = doc_root / "doc_002.json"
        doc2.write_text(
            json.dumps(
                {
                    "id": "doc_002",
                    "text": "Second document",
                    "metadata": {"project": "test-project"},
                }
            )
        )

        # Initialize stores and add annotations
        doc_store = DocumentStore(doc_root)
        ann_store = SQLiteAnnotationStore(db_path)

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

        yield doc_root, db_path


def test_export_project_creates_zip_file(test_project_setup, tmp_path):
    """Test that export_project creates a ZIP file with correct contents."""
    doc_root, db_path = test_project_setup

    # Initialize stores
    doc_store = DocumentStore(doc_root)
    ann_store = SQLiteAnnotationStore(db_path)

    output_path = tmp_path / "test-project.zip"

    # Call export_project
    stats = export_project(
        project="test-project",
        output_path=str(output_path),
        doc_store=doc_store,
        ann_store=ann_store,
    )

    # Verify ZIP file created
    assert output_path.exists()
    assert stats["zip_path"] == str(output_path)
    assert stats["documents_exported"] == 2
    assert stats["annotations_exported"] == 1
    assert stats["errors"] == 0

    # Verify ZIP contents
    with zipfile.ZipFile(output_path, "r") as zf:
        assert "doc_001.json" in zf.namelist()
        assert "doc_002.json" in zf.namelist()
        assert "doc_001.ann.json" in zf.namelist()


def test_export_project_default_output_path(test_project_setup):
    """Test that default output path is {project}.zip in current directory."""
    doc_root, db_path = test_project_setup

    # Initialize stores
    doc_store = DocumentStore(doc_root)
    ann_store = SQLiteAnnotationStore(db_path)

    # Change to doc_root (so we can clean up the ZIP file)
    original_cwd = os.getcwd()
    os.chdir(doc_root)

    try:
        # Call without output_path (should default to test-project.zip)
        stats = export_project(
            project="test-project", output_path=None, doc_store=doc_store, ann_store=ann_store
        )

        # Verify default path used
        expected_path = doc_root / "test-project.zip"
        assert Path(stats["zip_path"]).resolve() == expected_path.resolve()
        assert expected_path.exists()
    finally:
        os.chdir(original_cwd)


def test_export_nonexistent_project_returns_error(test_project_setup, tmp_path):
    """Test that exporting nonexistent project returns error stats."""
    doc_root, db_path = test_project_setup

    # Initialize stores
    doc_store = DocumentStore(doc_root)
    ann_store = SQLiteAnnotationStore(db_path)

    output_path = tmp_path / "nonexistent.zip"

    # Call export_project with nonexistent project
    stats = export_project(
        project="nonexistent",
        output_path=str(output_path),
        doc_store=doc_store,
        ann_store=ann_store,
    )

    # Verify error stats
    assert stats["documents_exported"] == 0
    assert stats["annotations_exported"] == 0
    assert stats["errors"] == 1
    assert "No documents found" in stats["error_message"]
    assert not output_path.exists()
