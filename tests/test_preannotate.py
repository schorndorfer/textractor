import json
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from textractor.api.dependencies import init_annotation_store, init_store, init_terminology
from textractor.api.main import create_app


@pytest.fixture
def client(tmp_path):
    """Create test client with temporary document storage"""
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    init_store(tmp_path)
    init_annotation_store(tmp_path / "test.db")
    init_terminology(snomed_dir=None)
    app = create_app()
    return TestClient(app)


@pytest.fixture
def sample_doc(tmp_path):
    """Create a sample document"""
    doc_id = "test_doc"
    (tmp_path / f"{doc_id}.json").write_text(
        json.dumps({"id": doc_id, "text": "Patient has chest pain.", "metadata": {}})
    )
    return doc_id


def test_preannotate_missing_api_key(tmp_path):
    """Test error when no LLM credentials are configured"""
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ.pop("AWS_BEARER_TOKEN_BEDROCK", None)

    doc_id = "test_doc"
    (tmp_path / f"{doc_id}.json").write_text(
        json.dumps({"id": doc_id, "text": "Patient has chest pain.", "metadata": {}})
    )

    init_store(tmp_path)
    init_annotation_store(tmp_path / "test.db")
    init_terminology(snomed_dir=None)
    app = create_app()
    client = TestClient(app)

    response = client.post(f"/api/documents/{doc_id}/preannotate")
    assert response.status_code == 500
    assert "LLM credentials not configured" in response.json()["detail"]

    # Restore for other tests
    os.environ["ANTHROPIC_API_KEY"] = "test-key"


def test_preannotate_document_not_found(client):
    """Test 404 when document doesn't exist"""
    response = client.post("/api/documents/nonexistent/preannotate")
    assert response.status_code == 404


def test_preannotate_document_locked(client, sample_doc):
    """Test 403 when document is completed"""
    from textractor.api.dependencies import get_annotation_store
    from textractor.api.models import AnnotationFile

    # Mark document as completed in SQLite
    ann_store = get_annotation_store()
    ann_store.save_annotations(
        doc_id=sample_doc,
        annotations=AnnotationFile(
            doc_id=sample_doc,
            spans=[],
            reasoning_steps=[],
            document_annotations=[],
            completed=True,
        ),
        annotator="default",
        source="human",
    )

    response = client.post(f"/api/documents/{sample_doc}/preannotate")
    assert response.status_code == 403
    assert "completed" in response.json()["detail"]


@patch("textractor.api.routers.preannotate.extract_medical_terms")
@patch("textractor.api.routers.preannotate.generate_annotations_raw")
@patch("textractor.api.routers.preannotate.validate_and_convert_annotations")
def test_preannotate_success(
    mock_validate, mock_generate, mock_extract, client, sample_doc
):
    """Test successful pre-annotation"""
    from textractor.api.models import AnnotationFile, Span

    mock_extract.return_value = ["chest pain"]
    mock_generate.return_value = {
        "spans": [{"start": 12, "end": 22, "text": "chest pain"}],
        "reasoning_steps": [],
        "document_annotations": [],
    }
    mock_validate.return_value = AnnotationFile(
        doc_id=sample_doc,
        spans=[Span(start=12, end=22, text="chest pain", source="model")],
        reasoning_steps=[],
        document_annotations=[],
    )

    response = client.post(f"/api/documents/{sample_doc}/preannotate")

    assert response.status_code == 200
    data = response.json()
    assert data["doc_id"] == sample_doc
    assert len(data["spans"]) == 1
    assert data["spans"][0]["text"] == "chest pain"
    assert data["spans"][0]["source"] == "model"


@patch("textractor.api.routers.preannotate.extract_medical_terms")
@patch("textractor.api.routers.preannotate.generate_annotations_raw")
@patch("textractor.api.routers.preannotate.validate_and_convert_annotations")
def test_preannotate_success_with_bedrock_token_only(
    mock_validate, mock_generate, mock_extract, tmp_path, sample_doc
):
    """Test pre-annotation works with Bedrock token when ANTHROPIC_API_KEY is missing."""
    from textractor.api.models import AnnotationFile, Span

    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ["AWS_BEARER_TOKEN_BEDROCK"] = "bedrock-test-token"

    init_store(tmp_path)
    init_annotation_store(tmp_path / "test.db")
    init_terminology(snomed_dir=None)
    app = create_app()
    client = TestClient(app)

    mock_extract.return_value = ["chest pain"]
    mock_generate.return_value = {
        "spans": [{"start": 12, "end": 22, "text": "chest pain"}],
        "reasoning_steps": [],
        "document_annotations": [],
    }
    mock_validate.return_value = AnnotationFile(
        doc_id=sample_doc,
        spans=[Span(start=12, end=22, text="chest pain", source="model")],
        reasoning_steps=[],
        document_annotations=[],
    )

    response = client.post(f"/api/documents/{sample_doc}/preannotate")

    assert response.status_code == 200
    data = response.json()
    assert data["doc_id"] == sample_doc

    os.environ.pop("AWS_BEARER_TOKEN_BEDROCK", None)
    os.environ["ANTHROPIC_API_KEY"] = "test-key"


@patch("textractor.api.routers.preannotate.extract_medical_terms")
@patch("textractor.api.routers.preannotate.generate_annotations_raw")
@patch("textractor.api.routers.preannotate.validate_and_convert_annotations")
def test_preannotate_bedrock_defaults_to_bedrock_model(
    mock_validate, mock_generate, mock_extract, tmp_path, sample_doc
):
    """Test Bedrock mode uses a Bedrock-compatible model when model env var is missing."""
    from textractor.api.models import AnnotationFile

    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ["AWS_BEARER_TOKEN_BEDROCK"] = "bedrock-test-token"
    os.environ.pop("TEXTRACTOR_LLM_MODEL", None)

    init_store(tmp_path)
    init_annotation_store(tmp_path / "test.db")
    init_terminology(snomed_dir=None)
    app = create_app()
    client = TestClient(app)

    mock_extract.return_value = ["chest pain"]
    mock_generate.return_value = {
        "spans": [],
        "reasoning_steps": [],
        "document_annotations": [],
    }
    mock_validate.return_value = AnnotationFile(
        doc_id=sample_doc,
        spans=[],
        reasoning_steps=[],
        document_annotations=[],
    )

    response = client.post(f"/api/documents/{sample_doc}/preannotate")
    assert response.status_code == 200

    assert mock_extract.called
    assert mock_generate.called
    assert mock_extract.call_args.kwargs["model"] == "anthropic.claude-sonnet-4-0-v1"
    assert mock_generate.call_args.kwargs["model"] == "anthropic.claude-sonnet-4-0-v1"

    os.environ.pop("AWS_BEARER_TOKEN_BEDROCK", None)
    os.environ["ANTHROPIC_API_KEY"] = "test-key"


def test_preannotate_rejects_direct_model_in_bedrock_mode(tmp_path, sample_doc):
    """Test clear 500 error for provider/model mismatch (Bedrock token + direct model name)."""
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ["AWS_BEARER_TOKEN_BEDROCK"] = "bedrock-test-token"
    os.environ["TEXTRACTOR_LLM_MODEL"] = "claude-sonnet-4-5"

    init_store(tmp_path)
    init_annotation_store(tmp_path / "test.db")
    init_terminology(snomed_dir=None)
    app = create_app()
    client = TestClient(app)

    response = client.post(f"/api/documents/{sample_doc}/preannotate")
    assert response.status_code == 500
    assert "Invalid TEXTRACTOR_LLM_MODEL for AWS Bedrock" in response.json()["detail"]

    os.environ.pop("AWS_BEARER_TOKEN_BEDROCK", None)
    os.environ.pop("TEXTRACTOR_LLM_MODEL", None)
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
