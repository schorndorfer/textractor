"""Tests for SQLite annotation store."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from textractor.api.annotation_store import SQLiteAnnotationStore
from textractor.api.models import AnnotationFile, Concept, DocumentAnnotation, ReasoningStep, Span


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield db_path


@pytest.fixture
def store(temp_db):
    """Create a SQLite annotation store."""
    return SQLiteAnnotationStore(temp_db)


@pytest.fixture
def sample_annotations():
    """Create sample annotations for testing."""
    return AnnotationFile(
        doc_id="test_doc_001",
        spans=[
            Span(
                id="span_001",
                start=0,
                end=10,
                text="chest pain",
                source="human",
            )
        ],
        reasoning_steps=[
            ReasoningStep(
                id="step_001",
                concept=Concept(
                    code="29857009",
                    display="Chest pain",
                    system="SNOMED-CT",
                ),
                span_ids=["span_001"],
                note="Primary symptom",
                source="human",
            )
        ],
        document_annotations=[
            DocumentAnnotation(
                id="ann_001",
                concept=Concept(
                    code="29857009",
                    display="Chest pain",
                    system="SNOMED-CT",
                ),
                evidence_span_ids=["span_001"],
                reasoning_step_ids=["step_001"],
                note="Patient complaint",
                category="symptom",
                source="human",
            )
        ],
        completed=False,
    )


# ── Basic CRUD Operations ────────────────────────────────────────────────────


def test_store_initialization(store, temp_db):
    """Test that store initializes database correctly."""
    assert temp_db.exists()
    assert store.db_path == temp_db


def test_save_and_get_annotations(store, sample_annotations):
    """Test saving and retrieving annotations."""
    # Save annotations
    version = store.save_annotations("test_doc_001", sample_annotations)
    assert version == 1

    # Retrieve annotations
    retrieved = store.get_annotations("test_doc_001")
    assert retrieved is not None
    assert retrieved.doc_id == "test_doc_001"
    assert len(retrieved.spans) == 1
    assert retrieved.spans[0].text == "chest pain"
    assert len(retrieved.reasoning_steps) == 1
    assert len(retrieved.document_annotations) == 1


def test_get_nonexistent_annotations(store):
    """Test retrieving annotations that don't exist."""
    result = store.get_annotations("nonexistent_doc")
    assert result is None


def test_delete_annotations(store, sample_annotations):
    """Test deleting annotations."""
    # Save annotations
    store.save_annotations("test_doc_001", sample_annotations)
    assert store.is_annotated("test_doc_001")

    # Delete annotations
    store.delete_annotations("test_doc_001")
    assert not store.is_annotated("test_doc_001")
    assert store.get_annotations("test_doc_001") is None


# ── Version History ───────────────────────────────────────────────────────────


def test_version_history(store, sample_annotations):
    """Test that each save creates a new version."""
    # Save version 1
    v1 = store.save_annotations("test_doc_001", sample_annotations, source="human")
    assert v1 == 1

    # Modify and save version 2
    sample_annotations.spans.append(
        Span(id="span_002", start=15, end=20, text="fever", source="human")
    )
    v2 = store.save_annotations("test_doc_001", sample_annotations, source="human")
    assert v2 == 2

    # Modify and save version 3
    sample_annotations.completed = True
    v3 = store.save_annotations("test_doc_001", sample_annotations, source="human")
    assert v3 == 3

    # Check history
    history = store.get_history("test_doc_001")
    assert len(history) == 3
    assert history[0]["version"] == 3  # Most recent first
    assert history[1]["version"] == 2
    assert history[2]["version"] == 1
    assert all(h["source"] == "human" for h in history)


def test_version_history_with_source_tracking(store, sample_annotations):
    """Test that source and model_name are tracked in version history."""
    # Save human annotation
    store.save_annotations("test_doc_001", sample_annotations, source="human")

    # Save AI annotation
    store.save_annotations(
        "test_doc_001",
        sample_annotations,
        source="model",
        model_name="claude-sonnet-4-5",
    )

    # Check history
    history = store.get_history("test_doc_001")
    assert len(history) == 2
    assert history[0]["source"] == "model"
    assert history[0]["model_name"] == "claude-sonnet-4-5"
    assert history[1]["source"] == "human"
    assert history[1]["model_name"] is None


def test_revert_to_version(store, sample_annotations):
    """Test reverting to a previous version."""
    # Save version 1 with 1 span
    v1 = store.save_annotations("test_doc_001", sample_annotations)
    assert v1 == 1

    # Save version 2 with 2 spans
    sample_annotations.spans.append(
        Span(id="span_002", start=15, end=20, text="fever", source="human")
    )
    v2 = store.save_annotations("test_doc_001", sample_annotations)
    assert v2 == 2

    # Verify version 2 is current
    current = store.get_annotations("test_doc_001")
    assert len(current.spans) == 2

    # Revert to version 1
    reverted = store.revert_to_version("test_doc_001", version=1)
    assert len(reverted.spans) == 1
    assert reverted.spans[0].text == "chest pain"

    # Check that a new version was created
    history = store.get_history("test_doc_001")
    assert len(history) == 3  # v1, v2, v3 (reverted)
    assert history[0]["version"] == 3

    # Verify current annotations match reverted version
    current = store.get_annotations("test_doc_001")
    assert len(current.spans) == 1


def test_revert_to_nonexistent_version(store):
    """Test reverting to a version that doesn't exist."""
    with pytest.raises(ValueError, match="Version 999 not found"):
        store.revert_to_version("test_doc_001", version=999)


# ── Multi-User Support ────────────────────────────────────────────────────────


def test_multiple_annotators(store, sample_annotations):
    """Test that different annotators maintain separate annotation versions."""
    # Annotator 1 saves
    v1_annotator1 = store.save_annotations("test_doc_001", sample_annotations, annotator="annotator1")
    assert v1_annotator1 == 1

    # Annotator 2 saves
    sample_annotations.spans[0].text = "modified by annotator2"
    v1_annotator2 = store.save_annotations("test_doc_001", sample_annotations, annotator="annotator2")
    assert v1_annotator2 == 1  # Separate version sequence

    # Annotator 1 saves again
    v2_annotator1 = store.save_annotations("test_doc_001", sample_annotations, annotator="annotator1")
    assert v2_annotator1 == 2

    # Verify separate histories
    history1 = store.get_history("test_doc_001", annotator="annotator1")
    history2 = store.get_history("test_doc_001", annotator="annotator2")
    assert len(history1) == 2
    assert len(history2) == 1

    # Verify separate retrieval
    ann1 = store.get_annotations("test_doc_001", annotator="annotator1")
    ann2 = store.get_annotations("test_doc_001", annotator="annotator2")
    assert ann1 is not None
    assert ann2 is not None


def test_delete_specific_annotator(store, sample_annotations):
    """Test deleting annotations for a specific annotator."""
    # Create annotations for two annotators
    store.save_annotations("test_doc_001", sample_annotations, annotator="annotator1")
    store.save_annotations("test_doc_001", sample_annotations, annotator="annotator2")

    # Verify both exist
    assert store.is_annotated("test_doc_001", annotator="annotator1")
    assert store.is_annotated("test_doc_001", annotator="annotator2")

    # Delete only annotator1
    store.delete_annotations("test_doc_001", annotator="annotator1")

    # Verify only annotator1 was deleted
    assert not store.is_annotated("test_doc_001", annotator="annotator1")
    assert store.is_annotated("test_doc_001", annotator="annotator2")


# ── Completed Status ──────────────────────────────────────────────────────────


def test_completed_status(store, sample_annotations):
    """Test completed status tracking."""
    # Initially not completed
    assert not store.is_completed("test_doc_001")

    # Save as not completed
    sample_annotations.completed = False
    store.save_annotations("test_doc_001", sample_annotations)
    assert not store.is_completed("test_doc_001")

    # Save as completed
    sample_annotations.completed = True
    store.save_annotations("test_doc_001", sample_annotations)
    assert store.is_completed("test_doc_001")

    # Verify retrieved annotations reflect completed status
    retrieved = store.get_annotations("test_doc_001")
    assert retrieved.completed is True


def test_set_completed(store, sample_annotations):
    """Test directly setting completed status."""
    # Save annotations
    store.save_annotations("test_doc_001", sample_annotations)

    # Set completed
    store.set_completed("test_doc_001", completed=True)
    assert store.is_completed("test_doc_001")

    # Set not completed
    store.set_completed("test_doc_001", completed=False)
    assert not store.is_completed("test_doc_001")


def test_completed_status_per_annotator(store, sample_annotations):
    """Test that completed status is tracked per annotator."""
    # Annotator 1 completes
    sample_annotations.completed = True
    store.save_annotations("test_doc_001", sample_annotations, annotator="annotator1")

    # Annotator 2 doesn't complete
    sample_annotations.completed = False
    store.save_annotations("test_doc_001", sample_annotations, annotator="annotator2")

    # Verify separate status
    assert store.is_completed("test_doc_001", annotator="annotator1")
    assert not store.is_completed("test_doc_001", annotator="annotator2")


# ── Annotation Status Checks ──────────────────────────────────────────────────


def test_is_annotated(store, sample_annotations):
    """Test checking if a document is annotated."""
    assert not store.is_annotated("test_doc_001")

    store.save_annotations("test_doc_001", sample_annotations)
    assert store.is_annotated("test_doc_001")


def test_is_annotated_per_annotator(store, sample_annotations):
    """Test checking annotation status per annotator."""
    store.save_annotations("test_doc_001", sample_annotations, annotator="annotator1")

    assert store.is_annotated("test_doc_001", annotator="annotator1")
    assert not store.is_annotated("test_doc_001", annotator="annotator2")


# ── Edge Cases ────────────────────────────────────────────────────────────────


def test_empty_annotations(store):
    """Test saving empty annotations."""
    empty_ann = AnnotationFile(
        doc_id="test_doc_001",
        spans=[],
        reasoning_steps=[],
        document_annotations=[],
        completed=False,
    )

    version = store.save_annotations("test_doc_001", empty_ann)
    assert version == 1

    retrieved = store.get_annotations("test_doc_001")
    assert retrieved is not None
    assert len(retrieved.spans) == 0
    assert len(retrieved.reasoning_steps) == 0
    assert len(retrieved.document_annotations) == 0


def test_large_annotation_set(store):
    """Test handling large annotation sets."""
    # Create annotations with many items
    large_ann = AnnotationFile(
        doc_id="test_doc_001",
        spans=[
            Span(id=f"span_{i}", start=i * 10, end=i * 10 + 5, text=f"text_{i}", source="human")
            for i in range(100)
        ],
        reasoning_steps=[
            ReasoningStep(
                id=f"step_{i}",
                concept=Concept(code=f"code_{i}", display=f"display_{i}", system="SNOMED-CT"),
                span_ids=[f"span_{i}"],
                source="human",
            )
            for i in range(50)
        ],
        document_annotations=[
            DocumentAnnotation(
                id=f"ann_{i}",
                concept=Concept(code=f"code_{i}", display=f"display_{i}", system="SNOMED-CT"),
                evidence_span_ids=[f"span_{i}"],
                reasoning_step_ids=[f"step_{i}"],
                category="symptom",
                source="human",
            )
            for i in range(25)
        ],
        completed=False,
    )

    store.save_annotations("test_doc_001", large_ann)
    retrieved = store.get_annotations("test_doc_001")

    assert len(retrieved.spans) == 100
    assert len(retrieved.reasoning_steps) == 50
    assert len(retrieved.document_annotations) == 25


def test_special_characters_in_doc_id(store, sample_annotations):
    """Test handling document IDs with special characters."""
    doc_ids = [
        "doc-with-dashes",
        "doc_with_underscores",
        "doc.with.dots",
        "doc/with/slashes",
        "doc@with#special$chars",
    ]

    for doc_id in doc_ids:
        sample_annotations.doc_id = doc_id
        store.save_annotations(doc_id, sample_annotations)
        retrieved = store.get_annotations(doc_id)
        assert retrieved is not None
        assert retrieved.doc_id == doc_id
