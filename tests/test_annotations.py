"""Tests for annotation API endpoints."""
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from textractor.api.main import create_app
from textractor.api.dependencies import init_annotation_store, init_store, init_terminology
from textractor.api.models import AnnotationFile, Span, ReasoningStep, DocumentAnnotation, Concept


@pytest.fixture
def client():
    """Create a test client with temporary storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        doc_root = Path(tmpdir)

        # Create a test document
        test_doc = doc_root / "test_001.json"
        test_doc.write_text('{"id": "test_001", "text": "Test document text", "metadata": {}}')

        # Initialize app dependencies
        init_store(doc_root)
        init_annotation_store(doc_root / "test.db")
        init_terminology(snomed_dir=None)  # No SNOMED needed for these tests

        app = create_app()
        yield TestClient(app)


def test_save_annotations_to_incomplete_document(client):
    """Test that annotations can be saved to an incomplete document."""
    # Create initial annotations
    ann = AnnotationFile(
        doc_id="test_001",
        spans=[Span(id="span_1", start=0, end=4, text="Test")],
        reasoning_steps=[],
        document_annotations=[],
        completed=False,
    )

    response = client.put("/api/documents/test_001/annotations", json=ann.model_dump())
    assert response.status_code == 200
    assert response.json()["completed"] is False


def test_cannot_edit_completed_document(client):
    """Test that completed documents cannot be edited (except to uncheck completed)."""
    # Create and save completed annotations
    ann = AnnotationFile(
        doc_id="test_001",
        spans=[Span(id="span_1", start=0, end=4, text="Test")],
        reasoning_steps=[],
        document_annotations=[],
        completed=True,
    )

    response = client.put("/api/documents/test_001/annotations", json=ann.model_dump())
    assert response.status_code == 200

    # Try to add a new span while completed
    ann_with_new_span = AnnotationFile(
        doc_id="test_001",
        spans=[
            Span(id="span_1", start=0, end=4, text="Test"),
            Span(id="span_2", start=5, end=13, text="document"),
        ],
        reasoning_steps=[],
        document_annotations=[],
        completed=True,  # Still completed
    )

    response = client.put("/api/documents/test_001/annotations", json=ann_with_new_span.model_dump())
    assert response.status_code == 403
    assert "Cannot modify annotations for a completed document" in response.json()["detail"]


def test_can_uncheck_completed_to_unlock(client):
    """Test that unchecking 'completed' allows the document to be unlocked."""
    # Create and save completed annotations
    ann = AnnotationFile(
        doc_id="test_001",
        spans=[Span(id="span_1", start=0, end=4, text="Test")],
        reasoning_steps=[],
        document_annotations=[],
        completed=True,
    )

    response = client.put("/api/documents/test_001/annotations", json=ann.model_dump())
    assert response.status_code == 200

    # Uncheck completed
    ann_unchecked = AnnotationFile(
        doc_id="test_001",
        spans=[Span(id="span_1", start=0, end=4, text="Test")],
        reasoning_steps=[],
        document_annotations=[],
        completed=False,  # Unchecked
    )

    response = client.put("/api/documents/test_001/annotations", json=ann_unchecked.model_dump())
    assert response.status_code == 200
    assert response.json()["completed"] is False


def test_can_edit_after_unlocking(client):
    """Test that documents can be edited after being unlocked."""
    # Create completed annotations
    ann = AnnotationFile(
        doc_id="test_001",
        spans=[Span(id="span_1", start=0, end=4, text="Test")],
        reasoning_steps=[],
        document_annotations=[],
        completed=True,
    )
    client.put("/api/documents/test_001/annotations", json=ann.model_dump())

    # Unlock
    ann.completed = False
    response = client.put("/api/documents/test_001/annotations", json=ann.model_dump())
    assert response.status_code == 200

    # Now add a new span
    ann.spans.append(Span(id="span_2", start=5, end=13, text="document"))
    response = client.put("/api/documents/test_001/annotations", json=ann.model_dump())
    assert response.status_code == 200
    assert len(response.json()["spans"]) == 2


def test_completed_with_full_annotations(client):
    """Test completing a document with full annotation structure."""
    # Create a complete annotation structure
    ann = AnnotationFile(
        doc_id="test_001",
        spans=[
            Span(id="span_1", start=0, end=4, text="Test"),
            Span(id="span_2", start=5, end=13, text="document"),
        ],
        reasoning_steps=[
            ReasoningStep(
                id="step_1",
                concept=Concept(code="123", display="Test Concept", system="SNOMED-CT"),
                span_ids=["span_1"],
                note="Test reasoning",
            )
        ],
        document_annotations=[
            DocumentAnnotation(
                id="ann_1",
                concept=Concept(code="456", display="Document Concept", system="SNOMED-CT"),
                evidence_span_ids=["span_1", "span_2"],
                reasoning_step_ids=["step_1"],
                note="Final annotation",
            )
        ],
        completed=False,
    )

    # Save incomplete version
    response = client.put("/api/documents/test_001/annotations", json=ann.model_dump())
    assert response.status_code == 200

    # Mark as completed
    ann.completed = True
    response = client.put("/api/documents/test_001/annotations", json=ann.model_dump())
    assert response.status_code == 200

    # Verify cannot modify
    ann.document_annotations[0].note = "Modified note"
    response = client.put("/api/documents/test_001/annotations", json=ann.model_dump())
    assert response.status_code == 403
