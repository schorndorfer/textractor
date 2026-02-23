"""Tests for document storage layer."""
import json
import tempfile
from pathlib import Path

import pytest

from textractor.api.storage import DocumentStore
from textractor.api.models import AnnotationFile, Document, Span, ReasoningStep, DocumentAnnotation, Concept


@pytest.fixture
def temp_store():
    """Create a temporary document store for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        store = DocumentStore(root)
        yield store


@pytest.fixture
def store_with_docs():
    """Create a store with sample documents for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        store = DocumentStore(root)

        # Create sample documents
        doc1 = Document(id="doc_001", text="First document text", metadata={"author": "Alice"})
        doc2 = Document(id="doc_002", text="Second document text", metadata={"author": "Bob"})
        doc3 = Document(id="doc_003", text="Third document text", metadata={})

        store.save_document(doc1)
        store.save_document(doc2)
        store.save_document(doc3)

        # Add annotations to doc_001 (incomplete)
        ann1 = AnnotationFile(
            doc_id="doc_001",
            spans=[Span(id="span_1", start=0, end=5, text="First")],
            reasoning_steps=[],
            document_annotations=[],
            completed=False,
        )
        store.save_annotations(ann1)

        # Add annotations to doc_002 (completed)
        ann2 = AnnotationFile(
            doc_id="doc_002",
            spans=[Span(id="span_2", start=0, end=6, text="Second")],
            reasoning_steps=[],
            document_annotations=[],
            completed=True,
        )
        store.save_annotations(ann2)

        yield store


class TestDocumentStoreInit:
    """Tests for DocumentStore initialization."""

    def test_creates_directory(self):
        """Test that __init__ creates the root directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "new_dir"
            assert not root.exists()

            store = DocumentStore(root)

            assert root.exists()
            assert root.is_dir()
            assert store.root == root

    def test_uses_existing_directory(self, temp_store):
        """Test that __init__ works with existing directories."""
        assert temp_store.root.exists()
        assert temp_store.root.is_dir()


class TestListDocuments:
    """Tests for list_documents method."""

    def test_empty_store(self, temp_store):
        """Test listing documents in an empty store."""
        docs = temp_store.list_documents()
        assert docs == []

    def test_lists_all_documents(self, store_with_docs):
        """Test that all documents are listed."""
        docs = store_with_docs.list_documents()
        assert len(docs) == 3

        doc_ids = {doc.id for doc in docs}
        assert doc_ids == {"doc_001", "doc_002", "doc_003"}

    def test_document_metadata(self, store_with_docs):
        """Test that document summaries include correct metadata."""
        docs = store_with_docs.list_documents()
        doc_map = {doc.id: doc for doc in docs}

        assert doc_map["doc_001"].metadata == {"author": "Alice"}
        assert doc_map["doc_002"].metadata == {"author": "Bob"}
        assert doc_map["doc_003"].metadata == {}

    def test_annotation_status(self, store_with_docs):
        """Test that annotation status is correctly reported."""
        docs = store_with_docs.list_documents()
        doc_map = {doc.id: doc for doc in docs}

        # doc_001 has annotations but not completed
        assert doc_map["doc_001"].is_annotated is True
        assert doc_map["doc_001"].is_completed is False

        # doc_002 has annotations and is completed
        assert doc_map["doc_002"].is_annotated is True
        assert doc_map["doc_002"].is_completed is True

        # doc_003 has no annotations
        assert doc_map["doc_003"].is_annotated is False
        assert doc_map["doc_003"].is_completed is False

    def test_text_preview(self, store_with_docs):
        """Test that text previews are limited to 200 characters."""
        docs = store_with_docs.list_documents()
        doc_map = {doc.id: doc for doc in docs}

        assert doc_map["doc_001"].text_preview == "First document text"
        assert len(doc_map["doc_001"].text_preview) <= 200

    def test_text_preview_truncation(self, temp_store):
        """Test that long text is truncated to 200 characters."""
        long_text = "A" * 500
        doc = Document(id="long_doc", text=long_text, metadata={})
        temp_store.save_document(doc)

        docs = temp_store.list_documents()
        assert len(docs) == 1
        assert docs[0].text_preview == "A" * 200

    def test_skips_annotation_files(self, store_with_docs):
        """Test that .ann.json files are not listed as documents."""
        docs = store_with_docs.list_documents()
        # Should only have 3 documents, not 5 (3 docs + 2 annotation files)
        assert len(docs) == 3

    def test_recursive_directory_scan(self, temp_store):
        """Test that documents in subdirectories are found."""
        # Create nested directory structure
        subdir = temp_store.root / "project1" / "subproject"
        subdir.mkdir(parents=True)

        doc1 = Document(id="root_doc", text="Root document", metadata={})
        doc2 = Document(id="nested_doc", text="Nested document", metadata={})

        # Save at different levels
        (temp_store.root / "root_doc.json").write_text(doc1.model_dump_json())
        (subdir / "nested_doc.json").write_text(doc2.model_dump_json())

        docs = temp_store.list_documents()
        assert len(docs) == 2
        doc_ids = {doc.id for doc in docs}
        assert doc_ids == {"root_doc", "nested_doc"}

    def test_handles_corrupt_document(self, temp_store):
        """Test that corrupt documents are skipped with warning."""
        # Create a corrupt JSON file
        corrupt_file = temp_store.root / "corrupt.json"
        corrupt_file.write_text("{invalid json")

        # Should not crash, just skip the corrupt file
        docs = temp_store.list_documents()
        assert docs == []

    def test_handles_corrupt_annotation(self, store_with_docs):
        """Test that corrupt annotation files don't crash listing."""
        # Corrupt the annotation file for doc_001
        ann_path = store_with_docs.root / "doc_001.ann.json"
        ann_path.write_text("{invalid json}")

        # Should still list documents, but with is_completed = False
        docs = store_with_docs.list_documents()
        doc_map = {doc.id: doc for doc in docs}

        assert doc_map["doc_001"].is_annotated is True
        assert doc_map["doc_001"].is_completed is False  # Can't read annotations


class TestGetDocument:
    """Tests for get_document method."""

    def test_get_existing_document(self, store_with_docs):
        """Test retrieving an existing document."""
        doc = store_with_docs.get_document("doc_001")

        assert doc is not None
        assert doc.id == "doc_001"
        assert doc.text == "First document text"
        assert doc.metadata == {"author": "Alice"}

    def test_get_nonexistent_document(self, temp_store):
        """Test that get_document returns None for nonexistent documents."""
        doc = temp_store.get_document("nonexistent")
        assert doc is None

    def test_document_fields(self, store_with_docs):
        """Test that all document fields are correctly deserialized."""
        doc = store_with_docs.get_document("doc_002")

        assert isinstance(doc, Document)
        assert doc.id == "doc_002"
        assert doc.text == "Second document text"
        assert doc.metadata == {"author": "Bob"}


class TestSaveDocument:
    """Tests for save_document method."""

    def test_save_new_document(self, temp_store):
        """Test saving a new document."""
        doc = Document(id="new_doc", text="New document text", metadata={"key": "value"})
        temp_store.save_document(doc)

        # Verify file was created
        doc_path = temp_store.root / "new_doc.json"
        assert doc_path.exists()

        # Verify content
        saved_doc = temp_store.get_document("new_doc")
        assert saved_doc is not None
        assert saved_doc.id == "new_doc"
        assert saved_doc.text == "New document text"
        assert saved_doc.metadata == {"key": "value"}

    def test_overwrite_existing_document(self, store_with_docs):
        """Test that save_document overwrites existing documents."""
        # Modify and save
        doc = Document(id="doc_001", text="Updated text", metadata={"new": "metadata"})
        store_with_docs.save_document(doc)

        # Verify changes
        saved_doc = store_with_docs.get_document("doc_001")
        assert saved_doc.text == "Updated text"
        assert saved_doc.metadata == {"new": "metadata"}

    def test_json_formatting(self, temp_store):
        """Test that JSON is formatted with indentation."""
        doc = Document(id="formatted_doc", text="Text", metadata={})
        temp_store.save_document(doc)

        doc_path = temp_store.root / "formatted_doc.json"
        content = doc_path.read_text()

        # Should be pretty-printed (contains newlines)
        assert "\n" in content
        assert "  " in content  # Indentation


class TestGetAnnotations:
    """Tests for get_annotations method."""

    def test_get_existing_annotations(self, store_with_docs):
        """Test retrieving existing annotations."""
        ann = store_with_docs.get_annotations("doc_001")

        assert ann.doc_id == "doc_001"
        assert len(ann.spans) == 1
        assert ann.spans[0].id == "span_1"
        assert ann.completed is False

    def test_get_nonexistent_annotations_returns_empty(self, temp_store):
        """Test that get_annotations returns empty AnnotationFile for nonexistent docs."""
        ann = temp_store.get_annotations("nonexistent")

        assert isinstance(ann, AnnotationFile)
        assert ann.doc_id == "nonexistent"
        assert ann.spans == []
        assert ann.reasoning_steps == []
        assert ann.document_annotations == []
        assert ann.completed is False

    def test_handles_corrupt_annotations(self, temp_store):
        """Test that corrupt annotation files return empty AnnotationFile."""
        # Create a document
        doc = Document(id="test_doc", text="Text", metadata={})
        temp_store.save_document(doc)

        # Create corrupt annotation file
        ann_path = temp_store.root / "test_doc.ann.json"
        ann_path.write_text("{invalid json}")

        # Should return empty annotations, not crash
        ann = temp_store.get_annotations("test_doc")
        assert ann.doc_id == "test_doc"
        assert ann.spans == []


class TestSaveAnnotations:
    """Tests for save_annotations method."""

    def test_save_new_annotations(self, temp_store):
        """Test saving annotations for a document."""
        ann = AnnotationFile(
            doc_id="test_doc",
            spans=[Span(id="span_1", start=0, end=5, text="Test")],
            reasoning_steps=[
                ReasoningStep(
                    id="step_1",
                    concept=Concept(code="123", display="Test Concept", system="SNOMED-CT"),
                    span_ids=["span_1"],
                )
            ],
            document_annotations=[
                DocumentAnnotation(
                    id="ann_1",
                    concept=Concept(code="123", display="Test Concept", system="SNOMED-CT"),
                    evidence_span_ids=[],
                    reasoning_step_ids=["step_1"],
                )
            ],
            completed=False,
        )

        temp_store.save_annotations(ann)

        # Verify file was created
        ann_path = temp_store.root / "test_doc.ann.json"
        assert ann_path.exists()

        # Verify content
        saved_ann = temp_store.get_annotations("test_doc")
        assert saved_ann.doc_id == "test_doc"
        assert len(saved_ann.spans) == 1
        assert len(saved_ann.reasoning_steps) == 1
        assert len(saved_ann.document_annotations) == 1
        assert saved_ann.completed is False

    def test_overwrite_annotations(self, store_with_docs):
        """Test that save_annotations overwrites existing annotations."""
        # Modify annotations
        ann = AnnotationFile(
            doc_id="doc_001",
            spans=[Span(id="new_span", start=10, end=15, text="Updated")],
            reasoning_steps=[],
            document_annotations=[],
            completed=True,
        )

        store_with_docs.save_annotations(ann)

        # Verify changes
        saved_ann = store_with_docs.get_annotations("doc_001")
        assert len(saved_ann.spans) == 1
        assert saved_ann.spans[0].id == "new_span"
        assert saved_ann.completed is True


class TestDocumentExists:
    """Tests for document_exists method."""

    def test_existing_document(self, store_with_docs):
        """Test document_exists for existing documents."""
        assert store_with_docs.document_exists("doc_001") is True
        assert store_with_docs.document_exists("doc_002") is True
        assert store_with_docs.document_exists("doc_003") is True

    def test_nonexistent_document(self, temp_store):
        """Test document_exists for nonexistent documents."""
        assert temp_store.document_exists("nonexistent") is False

    def test_only_checks_document_not_annotations(self, temp_store):
        """Test that document_exists only checks for document files, not annotations."""
        # Create only an annotation file, no document
        ann = AnnotationFile(doc_id="orphan", spans=[], reasoning_steps=[], document_annotations=[])
        temp_store.save_annotations(ann)

        # Should return False (no document file)
        assert temp_store.document_exists("orphan") is False


class TestPathMethods:
    """Tests for internal path methods."""

    def test_doc_path(self, temp_store):
        """Test _doc_path returns correct path."""
        path = temp_store._doc_path("test_123")
        assert path == temp_store.root / "test_123.json"

    def test_ann_path(self, temp_store):
        """Test _ann_path returns correct path."""
        path = temp_store._ann_path("test_123")
        assert path == temp_store.root / "test_123.ann.json"
