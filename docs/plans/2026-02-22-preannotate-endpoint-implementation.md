# LLM Pre-annotation Endpoint Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build POST /api/documents/{doc_id}/preannotate endpoint that uses Claude AI to generate structured clinical annotations with SNOMED validation and fuzzy span matching.

**Architecture:** Two-stage LLM pipeline (extract terms → generate annotations) with Anthropic tool calling for structured output, SNOMED database search for concept validation, and rapidfuzz for span offset recovery. Returns AnnotationFile without saving for frontend review.

**Tech Stack:** FastAPI, Pydantic, Anthropic Python SDK, rapidfuzz, SNOMED-CT

---

## Task 1: Add Anthropic Dependency

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add anthropic to dependencies**

In `pyproject.toml`, add to the `dependencies` list:

```toml
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "python-multipart>=0.0.12",
    "rapidfuzz>=3.14.3",
    "anthropic>=0.40.0",
]
```

**Step 2: Sync dependencies**

```bash
uv sync
```

Expected: Dependencies installed successfully

**Step 3: Verify import**

```bash
uv run python -c "import anthropic; print(f'Anthropic SDK version: {anthropic.__version__}')"
```

Expected: Prints version number (e.g., "Anthropic SDK version: 0.40.0")

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add anthropic SDK for LLM pre-annotation (Issue #41)

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: Create LLM Client Module - Extract Terms

**Files:**
- Create: `src/textractor/api/llm.py`
- Create: `tests/test_llm.py`

**Step 1: Write test for term extraction**

Create `tests/test_llm.py`:

```python
from unittest.mock import Mock, patch
from textractor.api.llm import extract_medical_terms


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
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_llm.py::test_extract_medical_terms -v
```

Expected: FAIL - module 'textractor.api.llm' not found

**Step 3: Create llm.py with extract_medical_terms**

Create `src/textractor/api/llm.py`:

```python
from __future__ import annotations

import logging
from typing import Any

import anthropic

logger = logging.getLogger(__name__)


def extract_medical_terms(text: str, api_key: str, model: str = "claude-sonnet-4-5") -> list[str]:
    """
    Extract medical terms from clinical text using Claude AI.

    Args:
        text: Clinical document text
        api_key: Anthropic API key
        model: Model name to use

    Returns:
        List of extracted medical terms

    Raises:
        ValueError: If LLM response is invalid
        anthropic.APIError: If API call fails
    """
    client = anthropic.Anthropic(api_key=api_key)

    tools = [
        {
            "name": "extract_medical_terms",
            "description": "Extract medical terms and concepts from clinical text",
            "input_schema": {
                "type": "object",
                "properties": {
                    "terms": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of medical terms, conditions, symptoms, or diagnoses",
                    }
                },
                "required": ["terms"],
            },
        }
    ]

    prompt = f"""Analyze this clinical document and extract all medical terms, conditions, symptoms, procedures, and diagnoses mentioned.

Clinical Text:
{text}

Return a list of medical terms that should be coded using clinical terminology (SNOMED-CT). Include:
- Diagnoses and conditions
- Symptoms and findings
- Procedures
- Medications (if present)
- Anatomical locations (if clinically relevant)

Be thorough but only include medically significant terms."""

    response = client.messages.create(
        model=model,
        max_tokens=1024,
        temperature=0.0,
        tools=tools,
        messages=[{"role": "user", "content": prompt}],
    )

    logger.info(f"Term extraction: stop_reason={response.stop_reason}, usage={response.usage}")

    if response.stop_reason != "tool_use":
        raise ValueError("LLM did not return structured output")

    tool_calls = [block for block in response.content if block.type == "tool_use"]
    if not tool_calls:
        raise ValueError("No tool calls found in LLM response")

    tool_input = tool_calls[0].input
    terms = tool_input.get("terms", [])

    logger.info(f"Extracted {len(terms)} medical terms")
    return terms
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_llm.py::test_extract_medical_terms -v
```

Expected: PASS

**Step 5: Run both tests**

```bash
uv run pytest tests/test_llm.py -v
```

Expected: Both tests PASS

**Step 6: Commit**

```bash
git add src/textractor/api/llm.py tests/test_llm.py
git commit -m "feat: add medical term extraction via Claude AI (Issue #41)

Stage 1 of two-stage annotation pipeline. Uses tool calling for
structured output.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: Add Annotation Generation

**Files:**
- Modify: `src/textractor/api/llm.py`
- Modify: `tests/test_llm.py`

**Step 1: Write test for annotation generation**

Add to `tests/test_llm.py`:

```python
from textractor.api.llm import generate_annotations_raw
from textractor.api.models import TerminologyConcept


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
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_llm.py::test_generate_annotations_raw -v
```

Expected: FAIL - function 'generate_annotations_raw' not found

**Step 3: Add generate_annotations_raw to llm.py**

Add to `src/textractor/api/llm.py`:

```python
from .models import TerminologyConcept


def generate_annotations_raw(
    text: str,
    snomed_candidates: list[TerminologyConcept],
    api_key: str,
    model: str = "claude-sonnet-4-5",
) -> dict[str, Any]:
    """
    Generate structured annotations using Claude AI with SNOMED context.

    Args:
        text: Clinical document text
        snomed_candidates: SNOMED concepts from terminology search
        api_key: Anthropic API key
        model: Model name to use

    Returns:
        Raw annotation data with indices (not IDs):
        {
            "spans": [{"start": int, "end": int, "text": str}, ...],
            "reasoning_steps": [{
                "concept_code": str,
                "concept_display": str,
                "span_indices": [int, ...],
                "note": str
            }, ...],
            "document_annotations": [{
                "concept_code": str,
                "concept_display": str,
                "evidence_span_indices": [int, ...],
                "reasoning_step_indices": [int, ...],
                "note": str
            }, ...]
        }

    Raises:
        ValueError: If LLM response is invalid
        anthropic.APIError: If API call fails
    """
    client = anthropic.Anthropic(api_key=api_key)

    # Format SNOMED candidates for prompt
    snomed_list = "\n".join(
        f"- {c.code}: {c.display}" for c in snomed_candidates
    )

    tools = [
        {
            "name": "annotate_document",
            "description": "Generate structured annotations for clinical text",
            "input_schema": {
                "type": "object",
                "properties": {
                    "spans": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "start": {"type": "integer"},
                                "end": {"type": "integer"},
                                "text": {"type": "string"},
                            },
                            "required": ["start", "end", "text"],
                        },
                    },
                    "reasoning_steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "concept_code": {"type": "string"},
                                "concept_display": {"type": "string"},
                                "span_indices": {"type": "array", "items": {"type": "integer"}},
                                "note": {"type": "string"},
                            },
                            "required": ["concept_code", "concept_display", "span_indices"],
                        },
                    },
                    "document_annotations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "concept_code": {"type": "string"},
                                "concept_display": {"type": "string"},
                                "evidence_span_indices": {"type": "array", "items": {"type": "integer"}},
                                "reasoning_step_indices": {"type": "array", "items": {"type": "integer"}},
                                "note": {"type": "string"},
                            },
                            "required": ["concept_code", "concept_display"],
                        },
                    },
                },
                "required": ["spans", "reasoning_steps", "document_annotations"],
            },
        }
    ]

    prompt = f"""Annotate this clinical document with structured information.

Clinical Text:
{text}

Available SNOMED-CT Concepts:
{snomed_list}

Instructions:
1. Identify text spans that provide evidence for clinical findings
2. Create reasoning steps linking spans to SNOMED concepts
3. Create document-level annotations for the primary diagnoses/findings
4. ONLY use SNOMED codes from the provided list above
5. Use span_indices and reasoning_step_indices to reference items by array position (0-indexed)
6. Be accurate - only annotate what is clearly stated in the text

Return structured annotations following the tool schema."""

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        temperature=0.0,
        tools=tools,
        messages=[{"role": "user", "content": prompt}],
    )

    logger.info(f"Annotation generation: stop_reason={response.stop_reason}, usage={response.usage}")

    if response.stop_reason != "tool_use":
        raise ValueError("LLM did not return structured output")

    tool_calls = [block for block in response.content if block.type == "tool_use"]
    if not tool_calls:
        raise ValueError("No tool calls found in LLM response")

    annotations = tool_calls[0].input

    logger.info(
        f"Generated {len(annotations.get('spans', []))} spans, "
        f"{len(annotations.get('reasoning_steps', []))} steps, "
        f"{len(annotations.get('document_annotations', []))} annotations"
    )

    return annotations
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_llm.py::test_generate_annotations_raw -v
```

Expected: PASS

**Step 5: Run all llm tests**

```bash
uv run pytest tests/test_llm.py -v
```

Expected: All 3 tests PASS

**Step 6: Commit**

```bash
git add src/textractor/api/llm.py tests/test_llm.py
git commit -m "feat: add structured annotation generation via Claude (Issue #41)

Stage 2 of pipeline. Generates spans, reasoning steps, and document
annotations using SNOMED context from terminology search.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: Add Span Validation and Recovery

**Files:**
- Modify: `src/textractor/api/llm.py`
- Modify: `tests/test_llm.py`

**Step 1: Write tests for span validation**

Add to `tests/test_llm.py`:

```python
from textractor.api.llm import validate_span, recover_span_offsets


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
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_llm.py -k "validate_span or recover_span" -v
```

Expected: FAIL - functions not found

**Step 3: Implement span validation functions**

Add to `src/textractor/api/llm.py`:

```python
from rapidfuzz import fuzz


def validate_span(span: dict[str, Any], doc_text: str) -> bool:
    """
    Check if span offsets are correct.

    Args:
        span: Span dict with 'start', 'end', 'text'
        doc_text: Full document text

    Returns:
        True if offsets are correct, False otherwise
    """
    try:
        actual_text = doc_text[span["start"] : span["end"]]
        return actual_text == span["text"]
    except IndexError:
        return False


def recover_span_offsets(
    span: dict[str, Any],
    doc_text: str,
    threshold: int = 90,
) -> tuple[int, int] | None:
    """
    Attempt to find correct offsets for a misaligned span using fuzzy matching.

    Args:
        span: Span dict with 'text'
        doc_text: Full document text
        threshold: Minimum similarity score (0-100)

    Returns:
        (new_start, new_end) tuple if found, None otherwise
    """
    span_text = span["text"]
    span_length = len(span_text)

    if span_length == 0 or span_length > len(doc_text):
        return None

    best_score = 0
    best_offset = None

    # Sliding window search
    for i in range(len(doc_text) - span_length + 1):
        window = doc_text[i : i + span_length]
        score = fuzz.ratio(span_text, window)

        if score > best_score:
            best_score = score
            best_offset = i

    if best_score >= threshold and best_offset is not None:
        return (best_offset, best_offset + span_length)

    return None
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_llm.py -k "validate_span or recover_span" -v
```

Expected: All 4 new tests PASS

**Step 5: Write test for full validation pipeline**

Add to `tests/test_llm.py`:

```python
from textractor.api.llm import validate_and_convert_annotations


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
```

**Step 6: Run test to verify it fails**

```bash
uv run pytest tests/test_llm.py::test_validate_and_convert_annotations -v
```

Expected: FAIL - function not found

**Step 7: Implement validate_and_convert_annotations**

Add to `src/textractor/api/llm.py`:

```python
from .models import AnnotationFile, Span, ReasoningStep, DocumentAnnotation, Concept


def validate_and_convert_annotations(
    raw_data: dict[str, Any],
    doc_text: str,
    doc_id: str,
    threshold: int = 90,
) -> AnnotationFile:
    """
    Validate span offsets, recover misaligned spans, and convert to AnnotationFile.

    Args:
        raw_data: Raw annotation data from LLM (with indices)
        doc_text: Full document text
        doc_id: Document ID
        threshold: Fuzzy matching threshold (0-100)

    Returns:
        AnnotationFile with validated spans and resolved references
    """
    raw_spans = raw_data.get("spans", [])
    raw_steps = raw_data.get("reasoning_steps", [])
    raw_anns = raw_data.get("document_annotations", [])

    # Validate and fix spans
    valid_spans = []
    invalid_span_indices = set()

    for idx, raw_span in enumerate(raw_spans):
        if validate_span(raw_span, doc_text):
            # Exact match - keep as is
            valid_spans.append(raw_span)
        else:
            # Try fuzzy recovery
            recovered = recover_span_offsets(raw_span, doc_text, threshold)
            if recovered:
                new_start, new_end = recovered
                raw_span["start"] = new_start
                raw_span["end"] = new_end
                valid_spans.append(raw_span)
                logger.info(f"Recovered span '{raw_span['text']}' at offset {new_start}")
            else:
                invalid_span_indices.add(idx)
                logger.warning(f"Discarded invalid span '{raw_span['text']}'")

    # Convert valid spans to Span objects with IDs and source='model'
    spans = [
        Span(
            start=s["start"],
            end=s["end"],
            text=s["text"],
            source="model",
        )
        for s in valid_spans
    ]

    # Build index mapping: old_index -> new span ID
    span_id_map = {i: spans[i].id for i in range(len(spans))}

    # Convert reasoning steps, cleaning span references
    reasoning_steps = []
    for step_data in raw_steps:
        # Filter out invalid span indices
        valid_span_ids = [
            span_id_map[idx]
            for idx in step_data.get("span_indices", [])
            if idx not in invalid_span_indices and idx in span_id_map
        ]

        step = ReasoningStep(
            concept=Concept(
                code=step_data["concept_code"],
                display=step_data["concept_display"],
                system="SNOMED-CT",
            ),
            span_ids=valid_span_ids,
            note=step_data.get("note", ""),
            source="model",
        )
        reasoning_steps.append(step)

    # Build index mapping: old_index -> new step ID
    step_id_map = {i: reasoning_steps[i].id for i in range(len(reasoning_steps))}

    # Convert document annotations, cleaning span and step references
    document_annotations = []
    for ann_data in raw_anns:
        # Filter out invalid span indices
        valid_evidence_span_ids = [
            span_id_map[idx]
            for idx in ann_data.get("evidence_span_indices", [])
            if idx not in invalid_span_indices and idx in span_id_map
        ]

        # Filter step indices
        valid_step_ids = [
            step_id_map[idx]
            for idx in ann_data.get("reasoning_step_indices", [])
            if idx in step_id_map
        ]

        ann = DocumentAnnotation(
            concept=Concept(
                code=ann_data["concept_code"],
                display=ann_data["concept_display"],
                system="SNOMED-CT",
            ),
            evidence_span_ids=valid_evidence_span_ids,
            reasoning_step_ids=valid_step_ids,
            note=ann_data.get("note", ""),
            source="model",
        )
        document_annotations.append(ann)

    logger.info(
        f"Validation complete: {len(valid_spans)}/{len(raw_spans)} spans valid, "
        f"{len(invalid_span_indices)} discarded"
    )

    return AnnotationFile(
        doc_id=doc_id,
        spans=spans,
        reasoning_steps=reasoning_steps,
        document_annotations=document_annotations,
        completed=False,
    )
```

**Step 8: Run test to verify it passes**

```bash
uv run pytest tests/test_llm.py::test_validate_and_convert_annotations -v
```

Expected: PASS

**Step 9: Run all llm tests**

```bash
uv run pytest tests/test_llm.py -v
```

Expected: All tests PASS

**Step 10: Commit**

```bash
git add src/textractor/api/llm.py tests/test_llm.py
git commit -m "feat: add span validation and fuzzy recovery (Issue #41)

Validates span offsets, uses rapidfuzz for recovery, cleans orphaned
references, and converts raw data to AnnotationFile with source='model'.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5: Create Preannotate Endpoint

**Files:**
- Create: `src/textractor/api/routers/preannotate.py`
- Create: `tests/test_preannotate.py`

**Step 1: Write endpoint tests**

Create `tests/test_preannotate.py`:

```python
import os
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from textractor.api.main import create_app


@pytest.fixture
def client(tmp_path):
    """Create test client with temporary document storage"""
    os.environ["TEXTRACTOR_DOC_ROOT"] = str(tmp_path)
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    app = create_app()
    return TestClient(app)


@pytest.fixture
def sample_doc(tmp_path):
    """Create a sample document"""
    import json

    doc_id = "test_doc"
    doc_path = tmp_path / f"{doc_id}.json"
    doc_path.write_text(
        json.dumps({"id": doc_id, "text": "Patient has chest pain.", "metadata": {}})
    )
    return doc_id


def test_preannotate_missing_api_key(client, sample_doc, tmp_path):
    """Test error when API key not configured"""
    del os.environ["ANTHROPIC_API_KEY"]

    # Recreate app without API key
    os.environ["TEXTRACTOR_DOC_ROOT"] = str(tmp_path)
    from textractor.api.main import create_app

    app = create_app()
    client = TestClient(app)

    response = client.post(f"/api/documents/{sample_doc}/preannotate")
    assert response.status_code == 500
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]

    # Restore for other tests
    os.environ["ANTHROPIC_API_KEY"] = "test-key"


def test_preannotate_document_not_found(client):
    """Test 404 when document doesn't exist"""
    response = client.post("/api/documents/nonexistent/preannotate")
    assert response.status_code == 404


def test_preannotate_document_locked(client, sample_doc, tmp_path):
    """Test 403 when document is completed"""
    import json

    # Create completed annotation file
    ann_path = tmp_path / f"{sample_doc}.ann.json"
    ann_path.write_text(
        json.dumps(
            {
                "doc_id": sample_doc,
                "spans": [],
                "reasoning_steps": [],
                "document_annotations": [],
                "completed": True,
            }
        )
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

    # Mock LLM responses
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
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_preannotate.py -v
```

Expected: FAIL - router not registered

**Step 3: Create preannotate router**

Create `src/textractor/api/routers/preannotate.py`:

```python
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_store, get_terminology
from ..enhanced_terminology import EnhancedTerminologyIndex
from ..llm import extract_medical_terms, generate_annotations_raw, validate_and_convert_annotations
from ..models import AnnotationFile
from ..storage import DocumentStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["preannotate"])


@router.post("/{doc_id}/preannotate", response_model=AnnotationFile)
def preannotate_document(
    doc_id: str,
    store: DocumentStore = Depends(get_store),
    terminology: EnhancedTerminologyIndex = Depends(get_terminology),
) -> AnnotationFile:
    """
    Generate AI annotations for a document using Claude AI.

    This endpoint:
    1. Extracts medical terms from the document
    2. Searches SNOMED for relevant concepts
    3. Generates structured annotations with validated SNOMED codes
    4. Returns annotations with source='model' for user review

    The annotations are NOT automatically saved - the frontend handles review
    and saving workflow.

    Args:
        doc_id: Document ID to annotate
        store: Document storage
        terminology: SNOMED terminology index

    Returns:
        AnnotationFile with generated annotations

    Raises:
        HTTPException 404: Document not found
        HTTPException 403: Document is locked/completed
        HTTPException 500: API key not configured
        HTTPException 502: LLM API error
    """
    # Check API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY environment variable not configured",
        )

    # Check document exists
    if not store.document_exists(doc_id):
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")

    # Check document isn't locked
    existing_annotations = store.get_annotations(doc_id)
    if existing_annotations.completed:
        raise HTTPException(
            status_code=403,
            detail="Cannot pre-annotate a completed document",
        )

    # Get document text
    doc = store.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")

    model = os.environ.get("TEXTRACTOR_LLM_MODEL", "claude-sonnet-4-5")

    try:
        # Stage 1: Extract medical terms
        logger.info(f"Extracting medical terms from document '{doc_id}'")
        terms = extract_medical_terms(doc.text, api_key=api_key, model=model)
        logger.info(f"Extracted {len(terms)} terms: {terms}")

        # Search SNOMED for each term
        snomed_candidates = []
        for term in terms:
            results = terminology.search(term, limit=5)
            snomed_candidates.extend(results)
            logger.info(f"SNOMED search for '{term}': {len(results)} results")

        if not snomed_candidates:
            logger.warning("No SNOMED candidates found for any term")

        # Stage 2: Generate annotations
        logger.info(f"Generating annotations with {len(snomed_candidates)} SNOMED candidates")
        raw_annotations = generate_annotations_raw(
            doc.text,
            snomed_candidates,
            api_key=api_key,
            model=model,
        )

        # Validate and convert
        threshold = int(os.environ.get("TEXTRACTOR_FUZZY_THRESHOLD", "90"))
        annotation_file = validate_and_convert_annotations(
            raw_annotations,
            doc.text,
            doc_id,
            threshold=threshold,
        )

        logger.info(
            f"Pre-annotation complete: {len(annotation_file.spans)} spans, "
            f"{len(annotation_file.reasoning_steps)} steps, "
            f"{len(annotation_file.document_annotations)} annotations"
        )

        return annotation_file

    except ValueError as e:
        logger.error(f"LLM validation error: {e}")
        raise HTTPException(status_code=502, detail=f"LLM response error: {str(e)}")
    except Exception as e:
        logger.error(f"Pre-annotation error: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Pre-annotation failed: {str(e)}")
```

**Step 4: Register router in main.py**

Modify `src/textractor/api/main.py`:

```python
from .routers import annotations, documents, preannotate
from .routers import terminology as terminology_router

# ... in create_app():

app.include_router(documents.router)
app.include_router(annotations.router)
app.include_router(preannotate.router)
app.include_router(terminology_router.router)
```

**Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_preannotate.py -v
```

Expected: All tests PASS

**Step 6: Test import doesn't break**

```bash
uv run python -c "from textractor.api.main import app; print('Import OK')"
```

Expected: "Import OK"

**Step 7: Commit**

```bash
git add src/textractor/api/routers/preannotate.py src/textractor/api/main.py tests/test_preannotate.py
git commit -m "feat: add POST /api/documents/{id}/preannotate endpoint (Issue #41)

Two-stage LLM pipeline with SNOMED validation and fuzzy span matching.
Returns AnnotationFile with source='model' for frontend review.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 6: Integration Testing

**Files:**
- Test: All components together

**Step 1: Run all tests**

```bash
uv run pytest -v
```

Expected: All tests PASS

**Step 2: Test backend startup with missing API key**

```bash
TEXTRACTOR_DOC_ROOT=./data/documents uv run python -c "from textractor.api.main import app; print('App created successfully')"
```

Expected: App starts (API key only checked when endpoint is called)

**Step 3: Create test document**

```bash
cat > data/documents/test_preannotate.json <<'EOF'
{
  "id": "test_preannotate",
  "text": "Patient presents with acute chest pain, hypertension, and type 2 diabetes mellitus. Physical exam reveals elevated blood pressure and tachycardia.",
  "metadata": {}
}
EOF
```

**Step 4: Test with mock API key (will fail, but validates flow)**

```bash
ANTHROPIC_API_KEY=invalid TEXTRACTOR_DOC_ROOT=./data/documents uv run python -c "
from textractor.api.main import create_app
from fastapi.testclient import TestClient

app = create_app()
client = TestClient(app)

# This will fail with 502 due to invalid key, but validates routing
response = client.post('/api/documents/test_preannotate/preannotate')
print(f'Status: {response.status_code}')
print(f'Response: {response.json()}')
"
```

Expected: Status 502 with API error (confirms endpoint is wired correctly)

**Step 5: Verify OpenAPI docs**

```bash
TEXTRACTOR_DOC_ROOT=./data/documents uv run python -c "
from textractor.api.main import create_app

app = create_app()
routes = [r.path for r in app.routes if hasattr(r, 'path')]
assert '/api/documents/{doc_id}/preannotate' in routes
print('✓ Preannotate endpoint registered in OpenAPI')
"
```

Expected: "✓ Preannotate endpoint registered in OpenAPI"

**Step 6: Update CLAUDE.md with new endpoint**

Add to `CLAUDE.md` in the Backend section:

```markdown
| `routers/preannotate.py` | `POST /api/documents/{id}/preannotate` — generates AI annotations using Claude, validates spans, returns AnnotationFile without auto-save |
```

Also add to Environment variables section:

```markdown
| `ANTHROPIC_API_KEY` | (required for pre-annotation) | Anthropic API key for Claude AI access |
| `TEXTRACTOR_LLM_MODEL` | `claude-sonnet-4-5` | Model name for annotation generation |
| `TEXTRACTOR_FUZZY_THRESHOLD` | `90` | Minimum similarity (0-100) for span recovery |
```

**Step 7: Commit documentation**

```bash
git add CLAUDE.md
git commit -m "docs: document pre-annotation endpoint and config (Issue #41)

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

**Step 8: Clean up test file**

```bash
rm data/documents/test_preannotate.json
```

---

## Task 7: Real API Testing (Optional)

**Note:** This task requires a real Anthropic API key. Skip if not available.

**Step 1: Set API key**

```bash
export ANTHROPIC_API_KEY="your-actual-api-key"
```

**Step 2: Start backend**

```bash
TEXTRACTOR_DOC_ROOT=./data/documents uv run textractor
```

**Step 3: Test endpoint with curl**

In another terminal:

```bash
curl -X POST http://localhost:8000/api/documents/note_001/preannotate | jq
```

**Step 4: Verify response**

Check that:
- Status: 200 OK
- Response has `spans`, `reasoning_steps`, `document_annotations`
- All entities have `"source": "model"`
- Span offsets are valid (can extract `doc.text[start:end]`)
- SNOMED codes exist in terminology database

**Step 5: Check logs**

Look for:
- "Extracting medical terms..."
- "Extracted N terms: [...]"
- "SNOMED search for '...'..."
- "Generating annotations with N SNOMED candidates"
- "Validation complete: X/Y spans valid..."
- "Pre-annotation complete: ..."

**Step 6: Test with locked document**

```bash
# Mark a document as completed
curl -X PUT http://localhost:8000/api/documents/note_001/annotations \
  -H "Content-Type: application/json" \
  -d '{"doc_id":"note_001","spans":[],"reasoning_steps":[],"document_annotations":[],"completed":true}'

# Try to pre-annotate (should fail with 403)
curl -X POST http://localhost:8000/api/documents/note_001/preannotate
```

Expected: 403 error

---

## Completion Checklist

- [ ] Anthropic SDK dependency added
- [ ] Medical term extraction implemented
- [ ] Annotation generation with SNOMED context implemented
- [ ] Span validation and fuzzy recovery implemented
- [ ] Preannotate endpoint created and registered
- [ ] All unit tests passing
- [ ] Integration tests passing
- [ ] Documentation updated
- [ ] Error handling for all scenarios
- [ ] Logging at appropriate levels
- [ ] Environment variables documented
- [ ] Optional: Real API testing completed

**Next Steps:**
- Create branch and PR referencing Issue #41
- Frontend work: Add "Pre-annotate" button (Issue #42)
- Consider prompt caching to reduce API costs
- Monitor span recovery success rates in production
