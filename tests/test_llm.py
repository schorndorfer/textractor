from unittest.mock import Mock, patch

from textractor.api.llm import (
    extract_medical_terms,
    generate_annotations_raw,
    recover_span_offsets,
    validate_and_convert_annotations,
    validate_span,
)
from textractor.api.models import TerminologyConcept


def test_extract_medical_terms():
    """Test medical term extraction from clinical text"""
    mock_response = Mock()
    mock_response.stop_reason = "tool_use"
    mock_response.content = [
        Mock(
            type="tool_use",
            name="extract_medical_terms",
            input={"terms": ["chest pain", "hypertension", "diabetes mellitus"]},
        )
    ]

    with patch("anthropic.Anthropic") as mock_client:
        mock_client.return_value.messages.create.return_value = mock_response

        text = "Patient with chest pain, hypertension, and diabetes mellitus."
        terms = extract_medical_terms(text, api_key="test-key", model="claude-sonnet-4-5")

        assert terms == ["chest pain", "hypertension", "diabetes mellitus"]
        assert mock_client.return_value.messages.create.called


def test_extract_medical_terms_no_tool_use():
    """Test error handling when LLM doesn't use tool"""
    mock_response = Mock()
    mock_response.stop_reason = "end_turn"
    mock_response.content = []

    with patch("anthropic.Anthropic") as mock_client:
        mock_client.return_value.messages.create.return_value = mock_response

        text = "Some text"
        try:
            extract_medical_terms(text, api_key="test-key", model="claude-sonnet-4-5")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "did not return structured output" in str(e)


# ── generate_annotations_raw ──────────────────────────────────────────────────

def test_generate_annotations_raw():
    """Test structured annotation generation"""
    mock_response = Mock()
    mock_response.stop_reason = "tool_use"
    mock_response.content = [
        Mock(
            type="tool_use",
            name="annotate_document",
            input={
                "spans": [
                    {"start": 0, "end": 10, "text": "chest pain"}
                ],
                "reasoning_steps": [
                    {
                        "concept_code": "29857009",
                        "concept_display": "Chest pain",
                        "span_indices": [0],
                        "note": "",
                    }
                ],
                "document_annotations": [
                    {
                        "concept_code": "29857009",
                        "concept_display": "Chest pain",
                        "evidence_span_indices": [0],
                        "reasoning_step_indices": [0],
                        "note": "",
                    }
                ],
            },
        )
    ]

    with patch("anthropic.Anthropic") as mock_client:
        mock_client.return_value.messages.create.return_value = mock_response

        text = "Patient with chest pain."
        snomed = [TerminologyConcept(code="29857009", display="Chest pain", system="SNOMED-CT")]
        result = generate_annotations_raw(text, snomed, api_key="test-key", model="claude-sonnet-4-5")

        assert len(result["spans"]) == 1
        assert result["spans"][0]["text"] == "chest pain"
        assert len(result["reasoning_steps"]) == 1
        assert result["reasoning_steps"][0]["concept_code"] == "29857009"


# ── validate_span ─────────────────────────────────────────────────────────────

def test_validate_span_exact_match():
    """Test span validation with exact match"""
    doc_text = "Patient has chest pain and fever."
    span = {"start": 12, "end": 22, "text": "chest pain"}

    assert validate_span(span, doc_text) is True


def test_validate_span_mismatch():
    """Test span validation with mismatch"""
    doc_text = "Patient has chest pain and fever."
    span = {"start": 10, "end": 20, "text": "chest pain"}  # Wrong offsets

    assert validate_span(span, doc_text) is False


# ── recover_span_offsets ──────────────────────────────────────────────────────

def test_recover_span_offsets_success():
    """Test span recovery with fuzzy matching"""
    doc_text = "Patient has chest pain and fever."
    span = {"start": 10, "end": 20, "text": "chest pain"}  # Wrong offsets

    result = recover_span_offsets(span, doc_text, threshold=90)

    assert result is not None
    new_start, new_end = result
    assert doc_text[new_start:new_end] == "chest pain"
    assert new_start == 12
    assert new_end == 22


def test_recover_span_offsets_failure():
    """Test span recovery when text not found"""
    doc_text = "Patient has chest pain and fever."
    span = {"start": 0, "end": 10, "text": "pneumonia"}  # Not in text

    result = recover_span_offsets(span, doc_text, threshold=90)

    assert result is None


# ── validate_and_convert_annotations ─────────────────────────────────────────

def test_validate_and_convert_annotations():
    """Test full annotation conversion with span validation"""
    doc_text = "Patient has chest pain and fever."
    raw_data = {
        "spans": [
            {"start": 12, "end": 22, "text": "chest pain"},  # Correct
            {"start": 20, "end": 25, "text": "fever"},  # Wrong, but recoverable
            {"start": 0, "end": 5, "text": "cough"},  # Not in text
        ],
        "reasoning_steps": [
            {
                "concept_code": "29857009",
                "concept_display": "Chest pain",
                "span_indices": [0],
                "note": "",
            },
            {
                "concept_code": "386661006",
                "concept_display": "Fever",
                "span_indices": [1, 2],  # 2 will be removed
                "note": "",
            },
        ],
        "document_annotations": [
            {
                "concept_code": "29857009",
                "concept_display": "Chest pain",
                "evidence_span_indices": [0, 2],  # 2 will be removed
                "reasoning_step_indices": [0],
                "note": "",
            }
        ],
    }

    result = validate_and_convert_annotations(raw_data, doc_text, "doc_001", threshold=90)

    # Should have 2 valid spans (0 and 1, with 1 recovered)
    assert len(result.spans) == 2
    assert result.spans[0].text == "chest pain"
    assert result.spans[1].text == "fever"
    assert result.spans[1].start == 27  # Recovered offset

    # Reasoning steps should have cleaned span_ids
    assert len(result.reasoning_steps) == 2
    assert len(result.reasoning_steps[0].span_ids) == 1
    assert len(result.reasoning_steps[1].span_ids) == 1  # Lost the invalid span

    # Document annotation should have cleaned evidence_span_ids
    assert len(result.document_annotations) == 1
    assert len(result.document_annotations[0].evidence_span_ids) == 1  # Lost the invalid span

    # All should have source='model'
    assert all(s.source == "model" for s in result.spans)
    assert all(s.source == "model" for s in result.reasoning_steps)
    assert all(a.source == "model" for a in result.document_annotations)
