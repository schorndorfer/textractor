# LLM Pre-annotation Endpoint Design

**Issue:** [#41](https://github.com/schorndorfer/textractor/issues/41)
**Date:** 2026-02-22
**Status:** Approved

## Overview

Add a `POST /api/documents/{doc_id}/preannotate` endpoint that uses Claude AI to automatically generate structured annotations (spans, reasoning steps, and document annotations) for clinical text documents. Results are returned to the frontend for user review before saving, with all generated items marked as `source: 'model'`.

## Requirements

1. Two-stage LLM pipeline: extract medical terms, then generate annotations
2. SNOMED concept validation via pre-searching the terminology database
3. Fuzzy matching for span offset recovery using `rapidfuzz`
4. Structured output via Anthropic's tool calling feature
5. Error handling for locked documents, API failures, and validation issues
6. Environment variable configuration for API key
7. Return annotations without saving (frontend handles review workflow)

## Dependencies

**New:**
- `anthropic` Python SDK (add to `pyproject.toml`)

**Existing:**
- `rapidfuzz>=3.14.3` (already in dependencies)
- Source field feature (Issue #40, merged in PR #46)
- SNOMED terminology search (`EnhancedTerminologyIndex`)

## Architecture

### Endpoint Specification

**Endpoint:** `POST /api/documents/{doc_id}/preannotate`

**Request:**
- No request body
- Document ID provided in URL path

**Response:** `AnnotationFile` (200 OK)
```json
{
  "doc_id": "note_001",
  "spans": [...],
  "reasoning_steps": [...],
  "document_annotations": [...],
  "completed": false
}
```

**Error Responses:**
- `404`: Document not found
- `403`: Document is locked/completed
- `500`: `ANTHROPIC_API_KEY` not configured
- `502`: Claude API failure or invalid LLM response

### Processing Flow

```
1. Validate document exists and isn't locked
2. Retrieve document text
3. Stage 1: Call Claude to extract medical terms
4. Search SNOMED database for each extracted term (top 5 per term)
5. Stage 2: Call Claude with document + SNOMED candidates to generate annotations
6. Generate IDs for all returned entities
7. Validate span offsets with fuzzy matching recovery
8. Filter invalid spans and clean orphaned references
9. Set source='model' on all entities
10. Return AnnotationFile to frontend
```

## Two-Stage Claude API Interaction

### Stage 1: Extract Medical Terms

**Purpose:** Identify medical concepts in the document that can be searched in SNOMED.

**API Call:**
- Model: `claude-sonnet-4-5` (configurable via `TEXTRACTOR_LLM_MODEL`)
- Method: Tool calling with structured output
- Temperature: 0.0 (deterministic)

**Tool Schema:**
```python
{
  "name": "extract_medical_terms",
  "description": "Extract medical terms and concepts from clinical text",
  "input_schema": {
    "type": "object",
    "properties": {
      "terms": {
        "type": "array",
        "items": {"type": "string"},
        "description": "List of medical terms, conditions, symptoms, or diagnoses found in the text"
      }
    },
    "required": ["terms"]
  }
}
```

**Prompt Template:**
```
Analyze this clinical document and extract all medical terms, conditions, symptoms, procedures, and diagnoses mentioned.

Clinical Text:
{document_text}

Return a list of medical terms that should be coded using clinical terminology (SNOMED-CT). Include:
- Diagnoses and conditions
- Symptoms and findings
- Procedures
- Medications (if present)
- Anatomical locations (if clinically relevant)

Be thorough but only include medically significant terms.
```

**Example Response:**
```json
{
  "terms": ["acute chest pain", "hypertension", "type 2 diabetes mellitus", "hyperlipidemia"]
}
```

---

### SNOMED Search

For each extracted term, search the SNOMED database:

```python
terminology = get_terminology()
snomed_candidates = []

for term in extracted_terms:
    results = terminology.search(term, limit=5)
    snomed_candidates.extend(results)
```

**Result format:**
```python
[
  {"code": "29857009", "display": "Chest pain", "system": "SNOMED-CT"},
  {"code": "38341003", "display": "Hypertensive disorder", "system": "SNOMED-CT"},
  ...
]
```

---

### Stage 2: Generate Structured Annotations

**Purpose:** Create spans, reasoning steps, and document annotations using validated SNOMED concepts.

**API Call:**
- Model: `claude-sonnet-4-5`
- Method: Tool calling with structured output
- Temperature: 0.0
- Context: Document text + SNOMED candidates

**Tool Schema:**
```python
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
            "start": {"type": "integer", "description": "Character offset start"},
            "end": {"type": "integer", "description": "Character offset end"},
            "text": {"type": "string", "description": "Text of the span"}
          },
          "required": ["start", "end", "text"]
        }
      },
      "reasoning_steps": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "concept_code": {"type": "string"},
            "concept_display": {"type": "string"},
            "span_indices": {
              "type": "array",
              "items": {"type": "integer"},
              "description": "Indices into the spans array"
            },
            "note": {"type": "string", "description": "Optional reasoning note"}
          },
          "required": ["concept_code", "concept_display", "span_indices"]
        }
      },
      "document_annotations": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "concept_code": {"type": "string"},
            "concept_display": {"type": "string"},
            "evidence_span_indices": {
              "type": "array",
              "items": {"type": "integer"}
            },
            "reasoning_step_indices": {
              "type": "array",
              "items": {"type": "integer"}
            },
            "note": {"type": "string"}
          },
          "required": ["concept_code", "concept_display"]
        }
      }
    },
    "required": ["spans", "reasoning_steps", "document_annotations"]
  }
}
```

**Prompt Template:**
```
Annotate this clinical document with structured information.

Clinical Text:
{document_text}

Available SNOMED-CT Concepts:
{formatted_snomed_candidates}

Instructions:
1. Identify text spans that provide evidence for clinical findings
2. Create reasoning steps linking spans to SNOMED concepts
3. Create document-level annotations for the primary diagnoses/findings
4. ONLY use SNOMED codes from the provided list above
5. Use span_indices and reasoning_step_indices to reference items by their array position (0-indexed)
6. Be accurate - only annotate what is clearly stated in the text

Return structured annotations following the tool schema.
```

**Note:** The tool schema uses indices (0, 1, 2...) to reference relationships. Server-side code generates UUIDs and resolves these index references after receiving the response.

## Span Validation and Recovery

After receiving Claude's response, validate that all span offsets are correct.

### Step 1: Exact Match Validation

```python
def validate_span(span, doc_text):
    actual_text = doc_text[span.start:span.end]
    return actual_text == span.text
```

### Step 2: Fuzzy Recovery

If exact match fails, attempt recovery using `rapidfuzz`:

```python
from rapidfuzz import fuzz, process

def recover_span_offsets(span, doc_text, threshold=90):
    """
    Attempt to find the correct offset for a misaligned span.

    Returns: (new_start, new_end) or None if unrecoverable
    """
    span_length = len(span.text)

    # Search in windows around the entire document
    best_match = None
    best_score = 0
    best_offset = 0

    # Sliding window search
    for i in range(len(doc_text) - span_length + 1):
        window = doc_text[i:i + span_length]
        score = fuzz.ratio(span.text, window)

        if score > best_score:
            best_score = score
            best_offset = i
            best_match = window

    if best_score >= threshold:
        return (best_offset, best_offset + span_length)

    return None
```

**Fuzzy Matching Parameters:**
- Similarity threshold: 90% (configurable via `TEXTRACTOR_FUZZY_THRESHOLD`)
- Scoring method: `rapidfuzz.fuzz.ratio` (Levenshtein-based similarity)
- Search scope: Entire document text

### Step 3: Clean Orphaned References

After identifying invalid spans:

```python
# Track which span indices are invalid
invalid_span_indices = set()

# Validate/recover all spans
valid_spans = []
for idx, raw_span in enumerate(raw_spans):
    if validate_span(raw_span, doc_text):
        valid_spans.append(raw_span)
    else:
        recovered = recover_span_offsets(raw_span, doc_text)
        if recovered:
            raw_span.start, raw_span.end = recovered
            valid_spans.append(raw_span)
        else:
            invalid_span_indices.add(idx)

# Clean reasoning steps
for step in reasoning_steps:
    step.span_ids = [
        span_id for i, span_id in enumerate(step.span_ids)
        if i not in invalid_span_indices
    ]

# Clean document annotations
for ann in document_annotations:
    ann.evidence_span_ids = [
        span_id for i, span_id in enumerate(ann.evidence_span_ids)
        if i not in invalid_span_indices
    ]
```

## Error Handling

### 1. Configuration Validation

```python
api_key = os.environ.get("ANTHROPIC_API_KEY")
if not api_key:
    raise HTTPException(
        status_code=500,
        detail="ANTHROPIC_API_KEY environment variable not configured"
    )
```

### 2. Document Access Control

```python
# Check document exists
if not store.document_exists(doc_id):
    raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")

# Check document isn't locked
annotations = store.get_annotations(doc_id)
if annotations.completed:
    raise HTTPException(
        status_code=403,
        detail="Cannot pre-annotate a completed document"
    )
```

### 3. Claude API Failures

```python
import anthropic

try:
    response = client.messages.create(...)
except anthropic.APIError as e:
    logger.error(f"Claude API error: {e}")
    raise HTTPException(
        status_code=502,
        detail=f"LLM API error: {str(e)}"
    )
```

### 4. Tool Use Validation

```python
if response.stop_reason != "tool_use":
    raise HTTPException(
        status_code=502,
        detail="LLM did not return structured output"
    )

tool_calls = [block for block in response.content if block.type == "tool_use"]
if not tool_calls:
    raise HTTPException(
        status_code=502,
        detail="No tool calls found in LLM response"
    )
```

### 5. Graceful Degradation

If all spans fail validation, still return the AnnotationFile with:
- Empty spans list
- Reasoning steps with empty `span_ids`
- Document annotations with empty `evidence_span_ids`

This lets users see what Claude attempted to identify, even if span extraction failed.

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes | - | Anthropic API key for Claude access |
| `TEXTRACTOR_LLM_MODEL` | No | `claude-sonnet-4-5` | Model name for annotation generation |
| `TEXTRACTOR_FUZZY_THRESHOLD` | No | `90` | Minimum similarity percentage for span recovery (0-100) |

### Model Selection

Recommended models:
- `claude-sonnet-4-5`: Best balance of quality and speed (default)
- `claude-opus-4`: Higher quality but slower and more expensive
- `claude-haiku-4`: Faster but potentially lower quality

## Implementation Details

### File Organization

**New files:**
- `src/textractor/api/routers/preannotate.py` - Endpoint implementation
- `src/textractor/api/llm.py` - Claude API client and prompt logic
- `tests/test_preannotate.py` - Unit and integration tests

**Modified files:**
- `src/textractor/api/main.py` - Register preannotate router
- `pyproject.toml` - Add `anthropic` dependency

### Key Functions

**`preannotate.py`:**
```python
@router.post("/{doc_id}/preannotate", response_model=AnnotationFile)
async def preannotate_document(
    doc_id: str,
    store: DocumentStore = Depends(get_store),
    terminology: EnhancedTerminologyIndex = Depends(get_terminology),
) -> AnnotationFile:
    """Generate AI annotations for a document."""
    # Main endpoint logic
```

**`llm.py`:**
```python
def extract_medical_terms(text: str, api_key: str, model: str) -> list[str]:
    """Stage 1: Extract medical terms from clinical text."""

def generate_annotations(
    text: str,
    snomed_candidates: list[TerminologyConcept],
    api_key: str,
    model: str
) -> dict:
    """Stage 2: Generate structured annotations using SNOMED context."""

def validate_and_fix_spans(
    raw_annotations: dict,
    doc_text: str,
    threshold: int = 90
) -> AnnotationFile:
    """Validate span offsets, attempt fuzzy recovery, clean references."""
```

## Testing Strategy

### Unit Tests

1. **Span validation:**
   - Test exact match validation
   - Test fuzzy recovery with various similarity levels
   - Test orphaned reference cleanup

2. **LLM response parsing:**
   - Test tool call extraction
   - Test index-to-ID resolution
   - Test error handling for malformed responses

3. **SNOMED search:**
   - Test term extraction and search
   - Test candidate formatting for prompts

### Integration Tests

1. **End-to-end happy path:**
   - Mock Claude API responses
   - Verify complete AnnotationFile generation
   - Verify `source: 'model'` on all entities

2. **Error scenarios:**
   - Document not found
   - Document locked
   - Missing API key
   - Claude API failure
   - All spans invalid

3. **Real API tests (optional, with API key):**
   - Test with actual Claude API
   - Verify quality of generated annotations
   - Use sample clinical notes

## Logging

**INFO level:**
- Endpoint called with doc_id
- Stage 1 complete: N terms extracted
- Stage 2 complete: X spans, Y steps, Z annotations
- Span validation: X/Y spans valid, Z recovered, W discarded

**WARNING level:**
- SNOMED search returned no results for term
- High number of invalid spans
- Reasoning step has no valid span references

**ERROR level:**
- Claude API failures
- Configuration errors
- Unexpected exceptions

## Future Enhancements

- **Batch processing:** Annotate multiple documents in one request
- **Async with progress:** Use background tasks + WebSocket for progress updates
- **Confidence scores:** Return Claude's confidence for each annotation
- **User feedback loop:** Learn from user corrections to improve prompts
- **Prompt caching:** Use Anthropic's prompt caching to reduce costs on repeated SNOMED context
- **Incremental annotation:** Only annotate new/changed sections of a document

## Success Criteria

1. Endpoint returns valid AnnotationFile with `source: 'model'` on all entities
2. Span offsets are >90% accurate (exact or fuzzy-recovered)
3. Generated SNOMED codes exist in the loaded terminology
4. Locked documents properly rejected with 403
5. API failures gracefully handled with 502
6. Response time < 30 seconds for typical clinical notes (100-500 words)
7. Frontend can load results as unsaved changes for review
