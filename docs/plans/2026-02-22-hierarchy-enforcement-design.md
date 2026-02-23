# Strict Hierarchy Enforcement for Pre-Annotations Design

**Issue:** [#50](https://github.com/schorndorfer/textractor/issues/50)
**Date:** 2026-02-22
**Status:** Approved

## Overview

Enforce strict hierarchical progression in AI-generated pre-annotations to eliminate redundant links and ensure complete traceability from document-level findings back through intermediate reasoning to text evidence.

## Requirements

**Goal:** Pre-annotations should strictly respect hierarchy: Spans (note-level) → Reasoning Steps (intermediate) → Document Annotations (document-level), without skipping levels.

**User Intent:**
> "I don't want the annotation graph this is generated to 'skip' levels - if there is a link from document to intermediate, and from intermediate to note level, then I don't need another link from document level to the same note level annotation"

**Scope:**
- **Strict hierarchy enforcement:** Every Document Annotation must reference ≥1 Reasoning Step, every Reasoning Step must reference ≥1 Span
- **No redundant links:** Document Annotations should NOT directly link to Spans (use `reasoning_step_ids` only, keep `evidence_span_ids` empty)
- **AI-only restriction:** Hierarchy rules apply only to AI-generated annotations (`source='model'`). Human annotations retain full flexibility.
- **Defense in depth:** Enforce via LLM tool schema constraints AND post-processing validation
- **Graceful degradation:** Filter out invalid annotations, log violations, return whatever is valid

**Success Criteria:**
1. LLM tool schema prevents `evidence_span_ids` in document annotations
2. Schema requires minimum 1 reasoning step per document annotation
3. Schema requires minimum 1 span per reasoning step
4. Post-processing validates hierarchy and filters violations
5. Detailed logging shows what was filtered and why
6. Human annotations unaffected
7. Backward compatible with existing data

## Architecture

### Approach: Defense in Depth with Schema + Validation

**Why this approach:**
- LLM tool schema guides Claude to create proper hierarchy
- Post-processing validation catches violations even if LLM ignores schema
- Consistent with existing filtering patterns (Issue #49 clinical filtering)
- Good observability through detailed logging
- Human flexibility preserved

**Validation Pipeline:**

```
extract_medical_terms()
    ↓
search SNOMED for each term
    ↓
generate_annotations_raw() → LLM follows updated schema (no evidence_span_indices, minItems: 1)
    ↓
validate_and_convert_annotations()
    ↓
Span validation (existing - fuzzy matching)
    ↓
Hierarchy validation (NEW):
  - Filter reasoning steps with 0 spans
  - Filter document annotations with 0 reasoning steps
  - Filter document annotations with non-empty evidence_span_ids
    ↓
Clinical filtering (existing - category-based)
    ↓
Return filtered AnnotationFile
```

## LLM Tool Schema Changes

### Remove Direct Span Links from Document Annotations

**File:** `src/textractor/api/llm.py` (lines ~165-200)

**Current schema (problematic):**

```python
"document_annotations": {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "concept_code": {"type": "string"},
            "concept_display": {"type": "string"},
            "evidence_span_indices": {"type": "array", "items": {"type": "integer"}},  # ALLOWS DIRECT LINKS
            "reasoning_step_indices": {"type": "array", "items": {"type": "integer"}},  # OPTIONAL
            "note": {"type": "string"},
            "category": {...}
        },
        "required": ["concept_code", "concept_display", "category"]
    }
}
```

**Updated schema (enforces hierarchy):**

```python
"document_annotations": {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "concept_code": {"type": "string"},
            "concept_display": {"type": "string"},
            # evidence_span_indices REMOVED - no direct span links allowed
            "reasoning_step_indices": {
                "type": "array",
                "items": {"type": "integer"},
                "minItems": 1  # NEW: Require at least 1 reasoning step
            },
            "note": {"type": "string"},
            "category": {
                "type": "string",
                "enum": [
                    "problem", "procedure", "medication", "lab", "symptom",
                    "diagnosis", "finding", "sign", "device", "allergy",
                    "demographic", "administrative", "temporal",
                    "social_history", "other"
                ]
            }
        },
        "required": ["concept_code", "concept_display", "category", "reasoning_step_indices"]
    }
}
```

**Key changes:**
- **Removed:** `evidence_span_indices` field entirely
- **Added:** `minItems: 1` to `reasoning_step_indices`
- **Made required:** `reasoning_step_indices` now in required array

### Enforce Minimum Spans in Reasoning Steps

**Current schema:**

```python
"reasoning_steps": {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "concept_code": {"type": "string"},
            "concept_display": {"type": "string"},
            "span_indices": {"type": "array", "items": {"type": "integer"}},  # CAN BE EMPTY
            "note": {"type": "string"}
        },
        "required": ["concept_code", "concept_display", "span_indices"]
    }
}
```

**Updated schema:**

```python
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
                "minItems": 1  # NEW: Require at least 1 span
            },
            "note": {"type": "string"}
        },
        "required": ["concept_code", "concept_display", "span_indices"]
    }
}
```

**Key change:**
- **Added:** `minItems: 1` to `span_indices` - every reasoning step must have text evidence

## Prompt Updates

### Add Hierarchy Instructions

**File:** `src/textractor/api/llm.py` (lines ~208-234)

**Add new instruction #5 about strict hierarchy:**

```python
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
5. STRICT HIERARCHY - follow this progression:
   - Spans (text evidence) → Reasoning Steps (intermediate concepts) → Document Annotations (final findings)
   - Every reasoning step MUST reference at least 1 span
   - Every document annotation MUST reference at least 1 reasoning step
   - Document annotations should NOT directly reference spans - only through reasoning steps
6. Use span_indices and reasoning_step_indices to reference items by array position (0-indexed)
7. Categorize each document annotation:
   - problem/diagnosis/finding: diseases, conditions, disorders
   - symptom/sign: patient complaints, clinical observations
   - procedure: therapeutic/diagnostic procedures
   - medication: drugs, pharmaceuticals
   - lab: laboratory tests and results
   - device: medical devices, implants
   - allergy: allergic reactions, intolerances
   - demographic: age, gender, race (NON-clinical)
   - administrative: visit info, insurance (NON-clinical)
   - social_history: smoking, alcohol (NON-clinical)
   - temporal: dates, times (NON-clinical)
   - other: anything else
8. Be accurate - only annotate what is clearly stated in the text

Return structured annotations following the tool schema."""
```

**Why this helps:**
- Explicitly explains WHY the schema is structured this way
- Clarifies the Spans → Steps → Annotations flow
- States minimum requirements (≥1 reference at each level)
- Reinforces "no direct span links" rule

## Post-Processing Validation Logic

### Add Hierarchy Validation in validate_and_convert_annotations()

**File:** `src/textractor/api/llm.py` (after line 443, before clinical filtering)

**Stage 1: Filter Reasoning Steps with No Spans**

```python
# ===== HIERARCHY VALIDATION (NEW) =====

# Stage 1: Filter reasoning steps with no spans
valid_reasoning_steps = []
filtered_steps_no_spans = 0

for step in reasoning_steps:
    if len(step.span_ids) == 0:
        filtered_steps_no_spans += 1
        logger.info(f"Filtered reasoning step with no spans: {step.concept.display}")
    else:
        valid_reasoning_steps.append(step)

# Rebuild step_id_map for valid steps only
step_id_map = {i: valid_reasoning_steps[i].id for i in range(len(valid_reasoning_steps))}
```

**Why this is needed:**
- LLM might ignore `minItems: 1` schema constraint
- Defense in depth: validate even if schema should prevent it
- Ensures every reasoning step has text evidence

**Stage 2: Filter Document Annotations with Violations**

```python
# Stage 2: Filter document annotations that violate hierarchy
valid_doc_annotations = []
filtered_anns_no_steps = 0
filtered_anns_direct_spans = 0

for ann in document_annotations:
    # Check for direct span links (should be empty for AI)
    if len(ann.evidence_span_ids) > 0:
        filtered_anns_direct_spans += 1
        logger.info(f"Filtered document annotation with direct span links: {ann.concept.display}")
        continue

    # Check for reasoning step requirement
    if len(ann.reasoning_step_ids) == 0:
        filtered_anns_no_steps += 1
        logger.info(f"Filtered document annotation with no reasoning steps: {ann.concept.display}")
        continue

    valid_doc_annotations.append(ann)
```

**Why this is needed:**
- Catches `evidence_span_ids` if LLM somehow includes it despite schema removal
- Validates minimum reasoning step requirement
- Ensures no "orphaned" document annotations

**Stage 3: Logging Summary**

```python
# Log hierarchy validation summary
if filtered_steps_no_spans > 0 or filtered_anns_no_steps > 0 or filtered_anns_direct_spans > 0:
    logger.info(
        f"Hierarchy validation: filtered {filtered_steps_no_spans} reasoning steps (no spans), "
        f"{filtered_anns_no_steps} document annotations (no reasoning steps), "
        f"{filtered_anns_direct_spans} document annotations (direct span links)"
    )

# ===== END HIERARCHY VALIDATION =====

# Continue with existing clinical filtering...
```

**Validation order in pipeline:**

1. Span validation (existing - fuzzy matching, offset recovery)
2. **Hierarchy validation (NEW)** - reasoning steps, document annotations
3. Clinical filtering (existing - category-based from Issue #49)
4. Return AnnotationFile

### Integration with Existing Filtering

The hierarchy validation runs **before** clinical filtering. This ensures:

1. First, enforce structural validity (hierarchy)
2. Then, enforce content validity (clinical categories)
3. Logs show both types of filtering separately
4. Easier to debug what was filtered and why

## Data Model Impact

### No Model Changes Required

**DocumentAnnotation remains unchanged:**

```python
class DocumentAnnotation(BaseModel):
    id: str = Field(default_factory=lambda: f"ann_{uuid4().hex[:8]}")
    concept: Concept
    evidence_span_ids: list[str] = Field(default_factory=list)  # KEPT for human flexibility
    reasoning_step_ids: list[str] = Field(default_factory=list)
    note: str = ""
    source: Literal["human", "model"] = "human"
    category: Optional[str] = None
```

**Why keep `evidence_span_ids`:**
- Human annotations retain full flexibility
- Backward compatibility with existing `.ann.json` files
- Only AI-generated annotations enforce empty `evidence_span_ids`
- Validation checks `source='model'` implicitly (happens in pre-annotation only)

**ReasoningStep remains unchanged:**

```python
class ReasoningStep(BaseModel):
    id: str = Field(default_factory=lambda: f"step_{uuid4().hex[:8]}")
    concept: Concept
    span_ids: list[str] = Field(default_factory=list)  # Still allows empty, but validated
    note: str = ""
    source: Literal["human", "model"] = "human"
```

**Why no Pydantic validators:**
- Validation only applies to pre-annotation generation
- Human annotations shouldn't trigger errors
- Simpler to validate in one place (llm.py) than model-wide

## Error Handling & Edge Cases

### Edge Case 1: All Document Annotations Filtered

**Scenario:** LLM generates document annotations but all violate hierarchy (no reasoning steps or have direct span links)

**Behavior:**
- Return empty `document_annotations` list
- Keep valid `reasoning_steps` and `spans`
- Log warning: "All document annotations filtered due to hierarchy violations"
- User sees spans and reasoning steps in UI but no document-level findings

**User action:** Can manually create document annotations from the reasoning steps

### Edge Case 2: All Reasoning Steps Filtered

**Scenario:** LLM generates reasoning steps but all have 0 spans

**Behavior:**
- Filter all reasoning steps
- Cascade effect: All document annotations become invalid (reference missing steps)
- Return empty AnnotationFile (0 spans, 0 steps, 0 annotations)
- Log warning: "All reasoning steps filtered (no spans) - cascade removed all document annotations"

**User action:** Can retry pre-annotation or manually annotate

### Edge Case 3: LLM Ignores Schema

**Scenario:** Despite schema changes, LLM still includes `evidence_span_indices` in response

**Behavior:**
- Post-processing validation catches it
- Filter document annotations with non-empty `evidence_span_ids`
- Log: "Filtered document annotation with direct span links: {concept}"
- Defense in depth protects against schema violations

**Why this might happen:**
- LLM might be creative and add unexpected fields
- Model update might change behavior
- Validation ensures system is robust

### Edge Case 4: Human Annotations with Direct Span Links

**Scenario:** User loads existing `.ann.json` file where human created document annotation with `evidence_span_ids` populated

**Behavior:**
- Load successfully (no validation on load)
- Display in UI correctly (annotation graph shows direct links)
- Only pre-annotation generation enforces hierarchy
- Human annotations retain full flexibility

**Why this is OK:**
- Hierarchy enforcement is for AI consistency, not human restriction
- Humans may have good reasons for direct links
- Backward compatibility preserved

### Edge Case 5: Partial Filtering

**Scenario:** Mixed valid/invalid items - some reasoning steps have spans, some don't

**Behavior:**
- Keep valid reasoning steps (with ≥1 span)
- Filter invalid reasoning steps (with 0 spans)
- Keep document annotations that reference valid steps only
- Filter document annotations that only reference invalid steps
- Log specific counts for each violation type

**Example:**
```
Hierarchy validation: filtered 2 reasoning steps (no spans),
1 document annotations (no reasoning steps),
0 document annotations (direct span links)
```

### Validation Order & Cascade Effects

**Validation pipeline order:**

```
1. Span validation (existing)
   - Validate offsets
   - Fuzzy recovery if misaligned
   - Discard invalid spans
   ↓
2. Hierarchy validation (NEW)
   - Filter reasoning steps with 0 spans
   - Filter document annotations with 0 reasoning steps
   - Filter document annotations with evidence_span_ids populated
   ↓
3. Clinical filtering (existing, Issue #49)
   - Filter non-clinical document annotations
   - Cascade delete orphaned reasoning steps and spans
   ↓
4. Return AnnotationFile
```

**Cascade effects:**
- Filtering reasoning steps → orphans document annotations → they get filtered
- Filtering document annotations → orphans reasoning steps → clinical filter removes them
- Filtering spans → invalidates reasoning steps → cascade to document annotations

**Why this order matters:**
1. Structural integrity first (hierarchy)
2. Content validity second (clinical categories)
3. Clean separation of concerns in logs

## Testing Strategy

### Unit Tests

**File:** `tests/test_llm.py`

**Test 1: Reasoning step with no spans is filtered**

```python
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
```

**Test 2: Document annotation with no reasoning steps is filtered**

```python
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
                "reasoning_step_indices": [],  # Invalid - no reasoning steps
                "category": "symptom",
            },
        ],
    }

    doc_text = "chest pain"
    result = validate_and_convert_annotations(raw_data, doc_text, "test_doc")

    # Document annotation should be filtered
    assert len(result.document_annotations) == 0

    # Reasoning step should be kept initially, but clinical filtering will remove it (orphaned)
    # This test focuses on document annotation filtering
```

**Test 3: Document annotation with direct span links is filtered**

```python
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

    # Note: Need to update validation logic to handle this -
    # currently evidence_span_indices doesn't exist in raw_data
    # This test assumes we convert to DocumentAnnotation first, then validate
```

**Test 4: Valid hierarchy passes through**

```python
def test_valid_hierarchy_passes():
    """Test that valid hierarchy is not filtered."""
    from textractor.api.llm import validate_and_convert_annotations

    raw_data = {
        "spans": [{"start": 0, "end": 10, "text": "chest pain"}],
        "reasoning_steps": [
            {
                "concept_code": "29857009",
                "concept_display": "Chest pain",
                "span_indices": [0],  # Valid - has span
            },
        ],
        "document_annotations": [
            {
                "concept_code": "29857009",
                "concept_display": "Chest pain",
                "reasoning_step_indices": [0],  # Valid - has reasoning step
                "category": "symptom",
            },
        ],
    }

    doc_text = "chest pain"
    result = validate_and_convert_annotations(raw_data, doc_text, "test_doc")

    # All should pass through
    assert len(result.spans) == 1
    assert len(result.reasoning_steps) == 1
    assert len(result.document_annotations) == 1
```

**Test 5: Cascade filtering when all steps invalid**

```python
def test_cascade_filter_all_steps_invalid():
    """Test that all annotations are filtered when all reasoning steps have no spans."""
    from textractor.api.llm import validate_and_convert_annotations

    raw_data = {
        "spans": [],  # No spans
        "reasoning_steps": [
            {
                "concept_code": "29857009",
                "concept_display": "Chest pain",
                "span_indices": [],  # Invalid - no spans
            },
        ],
        "document_annotations": [
            {
                "concept_code": "29857009",
                "concept_display": "Chest pain",
                "reasoning_step_indices": [0],
                "category": "symptom",
            },
        ],
    }

    doc_text = "chest pain"
    result = validate_and_convert_annotations(raw_data, doc_text, "test_doc")

    # Everything should be filtered
    assert len(result.spans) == 0
    assert len(result.reasoning_steps) == 0
    assert len(result.document_annotations) == 0
```

### Integration Tests

**Manual end-to-end testing:**

1. **Pre-annotate clinical note:**
   - Input: "Patient has chest pain and fever"
   - Click "✨ Pre-annotate"
   - Check backend logs for hierarchy validation
   - Expected: No filtering (valid hierarchy)

2. **Check annotation graph:**
   - Open annotation graph tab
   - Verify visual hierarchy: Spans → Reasoning Steps → Document Annotations
   - No direct edges from Document Annotations to Spans
   - Clean layered graph

3. **Verify saved JSON:**
   - Open `.ann.json` file
   - Check document_annotations
   - `evidence_span_ids` should be empty array
   - `reasoning_step_ids` should be populated

4. **Load existing human annotations:**
   - Open annotation with human-created direct span links
   - Verify it loads correctly
   - Verify annotation graph shows direct links (allowed for humans)

5. **Check logs for hierarchy violations:**
   - Look for: "Hierarchy validation: filtered X reasoning steps..."
   - Look for: "Filtered reasoning step with no spans: {concept}"
   - Verify counts match filtered items

## Files to Modify

**Backend:**
- `src/textractor/api/llm.py` - Update tool schema, prompt, add hierarchy validation

**Tests:**
- `tests/test_llm.py` - Add unit tests for hierarchy validation

**No model changes needed** - `evidence_span_ids` kept for backward compatibility

**No frontend changes needed** - purely backend validation

## Implementation Notes

**Where changes happen:**
- `generate_annotations_raw()` - schema and prompt updates (lines ~134-234)
- `validate_and_convert_annotations()` - hierarchy validation (after line 443)

**Validation sequence:**
1. Validate and fix spans (existing fuzzy matching)
2. Convert to Span/ReasoningStep/DocumentAnnotation objects
3. **Hierarchy validation (NEW):**
   - Filter reasoning steps with 0 spans
   - Filter document annotations with 0 reasoning steps or direct span links
4. Clinical filtering (existing from Issue #49)
5. Return AnnotationFile

**Logging verbosity:**
- Info level: Individual filtered items (for debugging)
- Info level: Summary statistics (counts by violation type)
- Warning level: All items filtered, empty results

**Schema enforcement:**
- `minItems: 1` is a JSON Schema validation constraint
- LLM should respect it, but we validate anyway
- Defense in depth: schema + post-processing

## Backward Compatibility

**Existing `.ann.json` files:**
- Load without issues
- `evidence_span_ids` field still exists in model
- No migration needed

**Human annotations:**
- Can still create direct span links if desired
- No validation on load or manual creation
- Only pre-annotation enforces hierarchy

**Frontend:**
- No changes required
- Annotation graph handles both patterns (direct and indirect)
- UI doesn't need to know about hierarchy enforcement

## Future Enhancements

**Potential improvements (not in scope):**

1. **Pydantic validators:** Add model-level validation with warnings (not errors) for human annotations
2. **Frontend UI guidance:** Visual hints in annotation creation showing recommended hierarchy
3. **Migration tool:** Convert existing direct span links to go through reasoning steps
4. **Hierarchy metrics:** API endpoint showing hierarchy compliance statistics
5. **Configurable enforcement:** Environment variable to disable hierarchy validation if needed

## Success Criteria

1. ✅ LLM tool schema removes `evidence_span_indices` from document_annotations
2. ✅ Schema requires `minItems: 1` for reasoning_step_indices
3. ✅ Schema requires `minItems: 1` for span_indices in reasoning_steps
4. ✅ Prompt explains strict hierarchy requirement
5. ✅ Post-processing validates and filters hierarchy violations
6. ✅ Reasoning steps with 0 spans are filtered
7. ✅ Document annotations with 0 reasoning steps are filtered
8. ✅ Document annotations with direct span links are filtered (AI only)
9. ✅ Detailed logging shows filtering statistics
10. ✅ Human annotations unaffected by hierarchy enforcement
11. ✅ Backward compatible with existing `.ann.json` files
12. ✅ Annotation graph displays clean hierarchy without redundant links
13. ✅ Unit tests cover all hierarchy validation scenarios
