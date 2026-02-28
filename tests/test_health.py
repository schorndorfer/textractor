"""Tests for the /health endpoint."""
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from textractor.api.dependencies import init_annotation_store, init_store, init_terminology
from textractor.api.main import create_app


@pytest.fixture
def client():
    """Test client with all dependencies initialized."""
    with tempfile.TemporaryDirectory() as tmpdir:
        doc_root = Path(tmpdir)
        init_store(doc_root)
        init_annotation_store(doc_root / "test.db")
        init_terminology(snomed_dir=None)
        app = create_app()
        yield TestClient(app)


@pytest.fixture
def client_with_docs():
    """Test client with pre-existing documents."""
    with tempfile.TemporaryDirectory() as tmpdir:
        doc_root = Path(tmpdir)

        # Write two document files
        (doc_root / "doc_001.json").write_text(
            '{"id": "doc_001", "text": "Patient has chest pain", "metadata": {}}'
        )
        (doc_root / "doc_002.json").write_text(
            '{"id": "doc_002", "text": "Follow-up visit", "metadata": {}}'
        )

        init_store(doc_root)
        init_annotation_store(doc_root / "test.db")
        init_terminology(snomed_dir=None)
        app = create_app()
        yield TestClient(app)


def test_health_returns_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_health_response_shape(client):
    resp = client.get("/health")
    body = resp.json()
    assert "status" in body
    assert "snomed_available" in body
    assert "doc_root_accessible" in body
    assert "document_count" in body
    assert "db_accessible" in body


def test_health_status_values(client):
    resp = client.get("/health")
    body = resp.json()
    assert body["status"] in ("healthy", "degraded")


def test_health_no_snomed(client):
    """Without SNOMED loaded, snomed_available should be False."""
    resp = client.get("/health")
    body = resp.json()
    assert body["snomed_available"] is False


def test_health_doc_root_accessible(client):
    resp = client.get("/health")
    body = resp.json()
    assert body["doc_root_accessible"] is True


def test_health_document_count_empty(client):
    resp = client.get("/health")
    body = resp.json()
    assert body["document_count"] == 0


def test_health_document_count_with_docs(client_with_docs):
    resp = client_with_docs.get("/health")
    body = resp.json()
    assert body["document_count"] == 2


def test_health_db_accessible(client):
    resp = client.get("/health")
    body = resp.json()
    assert body["db_accessible"] is True


def test_health_degraded_when_snomed_missing(client):
    """status is 'degraded' when snomed_available is False."""
    resp = client.get("/health")
    body = resp.json()
    # No SNOMED loaded → degraded
    assert body["status"] == "degraded"
