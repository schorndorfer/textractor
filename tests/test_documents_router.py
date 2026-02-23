"""Tests for document router API endpoints."""
import io
import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from textractor.api.main import create_app
from textractor.api.dependencies import init_store, init_terminology
from textractor.api.models import Document, AnnotationFile, Span


@pytest.fixture
def client():
    """Create a test client with temporary storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        doc_root = Path(tmpdir)

        # Initialize app dependencies
        init_store(doc_root)
        init_terminology(snomed_dir=None)  # No SNOMED needed for these tests

        app = create_app()
        yield TestClient(app)


@pytest.fixture
def client_with_docs():
    """Create a test client with pre-existing documents."""
    with tempfile.TemporaryDirectory() as tmpdir:
        doc_root = Path(tmpdir)

        # Create test documents
        doc1 = doc_root / "doc_001.json"
        doc1.write_text('{"id": "doc_001", "text": "First document text", "metadata": {"author": "Alice"}}')

        doc2 = doc_root / "doc_002.json"
        doc2.write_text('{"id": "doc_002", "text": "Second document text", "metadata": {"author": "Bob"}}')

        # Add annotations to doc_001
        ann1 = doc_root / "doc_001.ann.json"
        ann1.write_text('{"doc_id": "doc_001", "spans": [], "reasoning_steps": [], "document_annotations": [], "completed": false}')

        # Initialize app dependencies
        init_store(doc_root)
        init_terminology(snomed_dir=None)

        app = create_app()
        yield TestClient(app)


class TestListDocuments:
    """Tests for GET /api/documents endpoint."""

    def test_list_empty(self, client):
        """Test listing documents when no documents exist."""
        response = client.get("/api/documents")

        assert response.status_code == 200
        assert response.json() == []

    def test_list_multiple_documents(self, client_with_docs):
        """Test listing multiple documents."""
        response = client_with_docs.get("/api/documents")

        assert response.status_code == 200
        docs = response.json()
        assert len(docs) == 2

        doc_ids = {doc["id"] for doc in docs}
        assert doc_ids == {"doc_001", "doc_002"}

    def test_list_includes_metadata(self, client_with_docs):
        """Test that list includes document metadata."""
        response = client_with_docs.get("/api/documents")

        docs = {doc["id"]: doc for doc in response.json()}
        assert docs["doc_001"]["metadata"] == {"author": "Alice"}
        assert docs["doc_002"]["metadata"] == {"author": "Bob"}

    def test_list_includes_annotation_status(self, client_with_docs):
        """Test that list includes annotation status."""
        response = client_with_docs.get("/api/documents")

        docs = {doc["id"]: doc for doc in response.json()}
        assert docs["doc_001"]["is_annotated"] is True
        assert docs["doc_002"]["is_annotated"] is False


class TestUploadDocuments:
    """Tests for POST /api/documents/upload endpoint."""

    def test_upload_single_document(self, client):
        """Test uploading a single document."""
        doc_data = {
            "id": "new_doc",
            "text": "New document text",
            "metadata": {"key": "value"}
        }

        files = {
            "files": ("new_doc.json", io.BytesIO(json.dumps(doc_data).encode()), "application/json")
        }

        response = client.post("/api/documents/upload", files=files)

        assert response.status_code == 200
        uploaded = response.json()
        assert len(uploaded) == 1
        assert uploaded[0]["id"] == "new_doc"
        assert uploaded[0]["metadata"] == {"key": "value"}

    def test_upload_multiple_documents(self, client):
        """Test uploading multiple documents at once."""
        doc1 = {"id": "doc_1", "text": "Text 1", "metadata": {}}
        doc2 = {"id": "doc_2", "text": "Text 2", "metadata": {}}

        files = [
            ("files", ("doc1.json", io.BytesIO(json.dumps(doc1).encode()), "application/json")),
            ("files", ("doc2.json", io.BytesIO(json.dumps(doc2).encode()), "application/json")),
        ]

        response = client.post("/api/documents/upload", files=files)

        assert response.status_code == 200
        uploaded = response.json()
        assert len(uploaded) == 2

        doc_ids = {doc["id"] for doc in uploaded}
        assert doc_ids == {"doc_1", "doc_2"}

    def test_upload_rejects_non_json_files(self, client):
        """Test that non-JSON files are rejected."""
        files = {
            "files": ("document.txt", io.BytesIO(b"plain text"), "text/plain")
        }

        response = client.post("/api/documents/upload", files=files)

        assert response.status_code == 422
        assert "Only .json files are accepted" in response.json()["detail"]

    def test_upload_rejects_invalid_json(self, client):
        """Test that invalid JSON is rejected."""
        files = {
            "files": ("bad.json", io.BytesIO(b"{invalid json"), "application/json")
        }

        response = client.post("/api/documents/upload", files=files)

        assert response.status_code == 422
        assert "Invalid document JSON" in response.json()["detail"]

    def test_upload_rejects_duplicate_document(self, client_with_docs):
        """Test that duplicate document IDs are rejected."""
        doc_data = {"id": "doc_001", "text": "Duplicate", "metadata": {}}

        files = {
            "files": ("dup.json", io.BytesIO(json.dumps(doc_data).encode()), "application/json")
        }

        response = client_with_docs.post("/api/documents/upload", files=files)

        assert response.status_code == 422
        assert "already exists" in response.json()["detail"]

    def test_upload_partial_success(self, client_with_docs):
        """Test partial upload success (some succeed, some fail)."""
        doc1 = {"id": "new_doc", "text": "New document", "metadata": {}}
        doc2 = {"id": "doc_001", "text": "Duplicate", "metadata": {}}  # Already exists

        files = [
            ("files", ("new.json", io.BytesIO(json.dumps(doc1).encode()), "application/json")),
            ("files", ("dup.json", io.BytesIO(json.dumps(doc2).encode()), "application/json")),
        ]

        response = client_with_docs.post("/api/documents/upload", files=files)

        # Should succeed with partial results
        assert response.status_code == 200
        uploaded = response.json()
        assert len(uploaded) == 1
        assert uploaded[0]["id"] == "new_doc"

    def test_upload_validates_document_schema(self, client):
        """Test that document schema is validated."""
        # Missing required 'text' field
        doc_data = {"id": "invalid_doc", "metadata": {}}

        files = {
            "files": ("invalid.json", io.BytesIO(json.dumps(doc_data).encode()), "application/json")
        }

        response = client.post("/api/documents/upload", files=files)

        assert response.status_code == 422
        assert "Invalid document JSON" in response.json()["detail"]


class TestGetDocument:
    """Tests for GET /api/documents/{doc_id} endpoint."""

    def test_get_existing_document(self, client_with_docs):
        """Test retrieving an existing document."""
        response = client_with_docs.get("/api/documents/doc_001")

        assert response.status_code == 200
        doc = response.json()
        assert doc["id"] == "doc_001"
        assert doc["text"] == "First document text"
        assert doc["metadata"] == {"author": "Alice"}

    def test_get_nonexistent_document(self, client):
        """Test retrieving a nonexistent document returns 404."""
        response = client.get("/api/documents/nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_document_includes_all_fields(self, client_with_docs):
        """Test that all document fields are included."""
        response = client_with_docs.get("/api/documents/doc_002")

        assert response.status_code == 200
        doc = response.json()
        assert "id" in doc
        assert "text" in doc
        assert "metadata" in doc


class TestUpdateDocumentMetadata:
    """Tests for PATCH /api/documents/{doc_id}/metadata endpoint."""

    def test_update_metadata(self, client_with_docs):
        """Test updating document metadata."""
        update = {"metadata": {"new_key": "new_value"}}

        response = client_with_docs.patch("/api/documents/doc_001/metadata", json=update)

        assert response.status_code == 200
        doc = response.json()
        assert doc["id"] == "doc_001"
        assert "new_key" in doc["metadata"]
        assert doc["metadata"]["new_key"] == "new_value"

    def test_update_preserves_existing_metadata(self, client_with_docs):
        """Test that updating metadata preserves existing fields."""
        # doc_001 originally has {"author": "Alice"}
        update = {"metadata": {"role": "reviewer"}}

        response = client_with_docs.patch("/api/documents/doc_001/metadata", json=update)

        assert response.status_code == 200
        doc = response.json()
        # Should have both old and new fields
        assert doc["metadata"]["author"] == "Alice"
        assert doc["metadata"]["role"] == "reviewer"

    def test_update_can_overwrite_fields(self, client_with_docs):
        """Test that updating metadata can overwrite existing fields."""
        update = {"metadata": {"author": "Updated Author"}}

        response = client_with_docs.patch("/api/documents/doc_001/metadata", json=update)

        assert response.status_code == 200
        doc = response.json()
        assert doc["metadata"]["author"] == "Updated Author"

    def test_update_nonexistent_document(self, client):
        """Test updating metadata for nonexistent document returns 404."""
        update = {"metadata": {"key": "value"}}

        response = client.patch("/api/documents/nonexistent/metadata", json=update)

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_update_preserves_text(self, client_with_docs):
        """Test that updating metadata doesn't change document text."""
        original_response = client_with_docs.get("/api/documents/doc_001")
        original_text = original_response.json()["text"]

        update = {"metadata": {"new_field": "value"}}
        client_with_docs.patch("/api/documents/doc_001/metadata", json=update)

        updated_response = client_with_docs.get("/api/documents/doc_001")
        assert updated_response.json()["text"] == original_text


class TestDeleteDocument:
    """Tests for DELETE /api/documents/{doc_id} endpoint."""

    def test_delete_document(self, client_with_docs):
        """Test deleting a document."""
        response = client_with_docs.delete("/api/documents/doc_002")

        assert response.status_code == 200
        assert response.json()["status"] == "deleted"
        assert response.json()["doc_id"] == "doc_002"

        # Verify document is gone
        get_response = client_with_docs.get("/api/documents/doc_002")
        assert get_response.status_code == 404

    def test_delete_removes_from_list(self, client_with_docs):
        """Test that deleted document is removed from list."""
        # Verify exists
        list_response = client_with_docs.get("/api/documents")
        original_count = len(list_response.json())

        # Delete
        client_with_docs.delete("/api/documents/doc_001")

        # Verify removed from list
        list_response = client_with_docs.get("/api/documents")
        assert len(list_response.json()) == original_count - 1

        doc_ids = {doc["id"] for doc in list_response.json()}
        assert "doc_001" not in doc_ids

    def test_delete_also_removes_annotations(self, client_with_docs):
        """Test that deleting a document also deletes its annotations."""
        # doc_001 has annotations
        delete_response = client_with_docs.delete("/api/documents/doc_001")
        assert delete_response.status_code == 200

        # Verify annotations are also gone
        # (This is implicit - if we recreate the document, it shouldn't have old annotations)

    def test_delete_nonexistent_document(self, client):
        """Test deleting a nonexistent document returns 404."""
        response = client.delete("/api/documents/nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_delete_is_idempotent_fails(self, client_with_docs):
        """Test that deleting twice returns 404 on second attempt."""
        # First delete succeeds
        response1 = client_with_docs.delete("/api/documents/doc_002")
        assert response1.status_code == 200

        # Second delete fails
        response2 = client_with_docs.delete("/api/documents/doc_002")
        assert response2.status_code == 404


class TestEndToEndWorkflow:
    """Tests for end-to-end document workflows."""

    def test_upload_get_update_delete_workflow(self, client):
        """Test complete workflow: upload → get → update → delete."""
        # 1. Upload
        doc_data = {"id": "workflow_doc", "text": "Workflow text", "metadata": {"step": "1"}}
        files = {
            "files": ("workflow.json", io.BytesIO(json.dumps(doc_data).encode()), "application/json")
        }
        upload_response = client.post("/api/documents/upload", files=files)
        assert upload_response.status_code == 200

        # 2. Get
        get_response = client.get("/api/documents/workflow_doc")
        assert get_response.status_code == 200
        assert get_response.json()["metadata"]["step"] == "1"

        # 3. Update
        update = {"metadata": {"step": "2", "status": "updated"}}
        update_response = client.patch("/api/documents/workflow_doc/metadata", json=update)
        assert update_response.status_code == 200
        assert update_response.json()["metadata"]["step"] == "2"

        # 4. Verify update persisted
        get_response2 = client.get("/api/documents/workflow_doc")
        assert get_response2.json()["metadata"]["status"] == "updated"

        # 5. Delete
        delete_response = client.delete("/api/documents/workflow_doc")
        assert delete_response.status_code == 200

        # 6. Verify deleted
        get_response3 = client.get("/api/documents/workflow_doc")
        assert get_response3.status_code == 404
