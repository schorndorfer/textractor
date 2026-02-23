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
                "evidence_span_indices": [],  # No direct span links (hierarchy enforcement)
                "reasoning_step_indices": [0, 1],  # both steps referenced → neither orphaned
                "note": "",
                "category": "finding",  # Clinical - kept by filter
            }
        ],
    }

    result = validate_and_convert_annotations(raw_data, doc_text, "doc_001", threshold=90)

    # Should have 2 valid spans (0 and 1, with 1 recovered); span 2 (cough) discarded
    assert len(result.spans) == 2
    assert result.spans[0].text == "chest pain"
    assert result.spans[1].text == "fever"
    assert result.spans[1].start == 27  # Recovered offset

    # Both reasoning steps kept (both referenced by the document annotation)
    assert len(result.reasoning_steps) == 2
    assert len(result.reasoning_steps[0].span_ids) == 1
    assert len(result.reasoning_steps[1].span_ids) == 1  # Lost the invalid span

    # Document annotation should be kept (valid hierarchy: no direct links, has reasoning steps)
    assert len(result.document_annotations) == 1
    assert len(result.document_annotations[0].evidence_span_ids) == 0  # No direct span links

    # All should have source='model'
    assert all(s.source == "model" for s in result.spans)
    assert all(s.source == "model" for s in result.reasoning_steps)
    assert all(a.source == "model" for a in result.document_annotations)


def test_filter_non_clinical_annotations():
    """Test that non-clinical document annotations are filtered out."""
    from textractor.api.llm import validate_and_convert_annotations

    # Mock LLM response with mixed clinical and non-clinical annotations
    raw_data = {
        "spans": [
            {"start": 0, "end": 10, "text": "chest pain"},
            {"start": 14, "end": 30, "text": "68 year old male"},
        ],
        "reasoning_steps": [
            {
                "concept_code": "29857009",
                "concept_display": "Chest pain",
                "span_indices": [0],
                "note": "Patient symptom",
            },
            {
                "concept_code": "248153007",
                "concept_display": "Male",
                "span_indices": [1],
                "note": "Patient demographics",
            },
        ],
        "document_annotations": [
            {
                "concept_code": "29857009",
                "concept_display": "Chest pain",
                "evidence_span_indices": [],  # No direct span links (hierarchy enforcement)
                "reasoning_step_indices": [0],
                "note": "Primary complaint",
                "category": "symptom",  # Clinical - should be kept
            },
            {
                "concept_code": "248153007",
                "concept_display": "Male gender",
                "evidence_span_indices": [],  # No direct span links (hierarchy enforcement)
                "reasoning_step_indices": [1],
                "note": "Patient gender",
                "category": "demographic",  # Non-clinical - should be filtered
            },
        ],
    }

    doc_text = "chest pain in 68 year old male"
    result = validate_and_convert_annotations(raw_data, doc_text, "test_doc")

    # Should keep only clinical annotation
    assert len(result.document_annotations) == 1
    assert result.document_annotations[0].concept.display == "Chest pain"
    assert result.document_annotations[0].category == "symptom"

    # Should cascade delete orphaned reasoning step and span
    assert len(result.reasoning_steps) == 1
    assert result.reasoning_steps[0].concept.display == "Chest pain"

    assert len(result.spans) == 1
    assert result.spans[0].text == "chest pain"


def test_filter_all_annotations_returns_empty():
    """Test that filtering all annotations returns empty AnnotationFile."""
    from textractor.api.llm import validate_and_convert_annotations

    raw_data = {
        "spans": [
            {"start": 0, "end": 16, "text": "68 year old male"},
        ],
        "reasoning_steps": [
            {
                "concept_code": "248153007",
                "concept_display": "Male",
                "span_indices": [0],
                "note": "Demographics",
            },
        ],
        "document_annotations": [
            {
                "concept_code": "248153007",
                "concept_display": "Male gender",
                "evidence_span_indices": [],  # No direct span links
                "reasoning_step_indices": [0],
                "category": "demographic",  # Non-clinical
            },
        ],
    }

    doc_text = "68 year old male"
    result = validate_and_convert_annotations(raw_data, doc_text, "test_doc")

    # All should be filtered
    assert len(result.document_annotations) == 0
    assert len(result.reasoning_steps) == 0
    assert len(result.spans) == 0


def test_filter_reasoning_step_no_spans():
    """Test that reasoning steps with 0 spans are filtered."""
    from textractor.api.llm import validate_and_convert_annotations

    raw_data = {
        "spans": [
            {"start": 0, "end": 10, "text": "chest pain"},
        ],
        "reasoning_steps": [
            {
                "concept_code": "29857009",
                "concept_display": "Chest pain",
                "span_indices": [0],  # Valid - has span
            },
            {
                "concept_code": "12345",
                "concept_display": "Invalid concept",
                "span_indices": [],  # Invalid - no spans
            },
        ],
        "document_annotations": [
            {
                "concept_code": "29857009",
                "concept_display": "Chest pain",
                "evidence_span_indices": [],
                "reasoning_step_indices": [0],
                "category": "symptom",
            },
        ],
    }

    doc_text = "chest pain"
    result = validate_and_convert_annotations(raw_data, doc_text, "test_doc")

    # Should keep only valid reasoning step
    assert len(result.reasoning_steps) == 1
    assert result.reasoning_steps[0].concept.display == "Chest pain"

    # Document annotation should still be valid
    assert len(result.document_annotations) == 1


def test_filter_document_annotation_no_steps():
    """Test that document annotations with 0 reasoning steps are filtered."""
    from textractor.api.llm import validate_and_convert_annotations

    raw_data = {
        "spans": [{"start": 0, "end": 10, "text": "chest pain"}],
        "reasoning_steps": [
            {
                "concept_code": "29857009",
                "concept_display": "Chest pain",
                "span_indices": [0],
            },
        ],
        "document_annotations": [
            {
                "concept_code": "29857009",
                "concept_display": "Chest pain",
                "evidence_span_indices": [],
                "reasoning_step_indices": [],  # Invalid - no reasoning steps
                "category": "symptom",
            },
        ],
    }

    doc_text = "chest pain"
    result = validate_and_convert_annotations(raw_data, doc_text, "test_doc")

    # Document annotation should be filtered
    assert len(result.document_annotations) == 0


def test_filter_document_annotation_direct_spans():
    """Test that document annotations with evidence_span_ids are filtered."""
    from textractor.api.llm import validate_and_convert_annotations

    raw_data = {
        "spans": [{"start": 0, "end": 10, "text": "chest pain"}],
        "reasoning_steps": [
            {
                "concept_code": "29857009",
                "concept_display": "Chest pain",
                "span_indices": [0],
            },
        ],
        "document_annotations": [
            {
                "concept_code": "29857009",
                "concept_display": "Chest pain",
                "evidence_span_indices": [0],  # Invalid - direct span links
                "reasoning_step_indices": [0],
                "category": "symptom",
            },
        ],
    }

    doc_text = "chest pain"
    result = validate_and_convert_annotations(raw_data, doc_text, "test_doc")

    # Document annotation should be filtered (has direct span links)
    assert len(result.document_annotations) == 0


def test_filter_missing_category_treated_as_unknown():
    """Test that annotations without category are filtered out."""
    from textractor.api.llm import validate_and_convert_annotations

    raw_data = {
        "spans": [
            {"start": 0, "end": 10, "text": "chest pain"},
        ],
        "reasoning_steps": [
            {
                "concept_code": "29857009",
                "concept_display": "Chest pain",
                "span_indices": [0],
            },
        ],
        "document_annotations": [
            {
                "concept_code": "29857009",
                "concept_display": "Chest pain",
                "evidence_span_indices": [],  # No direct span links
                "reasoning_step_indices": [0],
                # category field intentionally missing
            },
        ],
    }

    doc_text = "chest pain"
    result = validate_and_convert_annotations(raw_data, doc_text, "test_doc")

    # Should be filtered (treated as category="unknown")
    assert len(result.document_annotations) == 0
