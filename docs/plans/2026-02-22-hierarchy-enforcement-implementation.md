# Hierarchy Enforcement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enforce strict hierarchical progression in AI-generated pre-annotations: Spans → Reasoning Steps → Document Annotations, eliminating redundant direct links.

**Architecture:** Update LLM tool schema to remove `evidence_span_indices` from document annotations and add `minItems: 1` constraints. Add hierarchy validation in `validate_and_convert_annotations()` to filter reasoning steps with no spans and document annotations with no reasoning steps or direct span links. Defense in depth: schema guides LLM, validation enforces.

**Tech Stack:** Python, Pydantic, Anthropic Claude API, pytest

---

## Task 1: Write Test for Reasoning Step Filtering (No Spans)

**Files:**
- Modify: `tests/test_llm.py` (add new test)

**Step 1: Write failing test**

Add this test to `tests/test_llm.py`:

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
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_llm.py::test_filter_reasoning_step_no_spans -v
```

Expected: FAIL (filtering not implemented yet, will keep both reasoning steps)

**Step 3: Implement hierarchy validation - filter reasoning steps with no spans**

In `src/textractor/api/llm.py`, find the `validate_and_convert_annotations()` function. After line 443 (after existing clinical filtering code), add hierarchy validation:

```python
def validate_and_convert_annotations(
    raw_data: dict[str, Any],
    doc_text: str,
    doc_id: str,
    threshold: int = 90,
) -> AnnotationFile:
    """
    Validate span offsets, recover misaligned spans, and convert to AnnotationFile.
    ...
    """
    # ... existing span validation code ...
    # ... existing reasoning step and document annotation conversion ...
    # ... existing clinical filtering code (around line 443) ...

    # ===== HIERARCHY VALIDATION (NEW - add after clinical filtering) =====

    # Stage 1: Filter reasoning steps with no spans
    valid_reasoning_steps = []
    filtered_steps_no_spans = 0

    for step in clinical_steps:  # Use clinical_steps from clinical filtering
        if len(step.span_ids) == 0:
            filtered_steps_no_spans += 1
            logger.info(f"Filtered reasoning step with no spans: {step.concept.display}")
        else:
            valid_reasoning_steps.append(step)

    # Rebuild step ID set for next stage
    valid_step_ids = {step.id for step in valid_reasoning_steps}

    # ===== END HIERARCHY VALIDATION STAGE 1 =====

    # Update return to use valid_reasoning_steps instead of clinical_steps
    return AnnotationFile(
        doc_id=doc_id,
        spans=clinical_spans,
        reasoning_steps=valid_reasoning_steps,  # Changed from clinical_steps
        document_annotations=clinical_annotations,
        completed=False,
    )
```

Wait - I need to reconsider the order. The design says hierarchy validation should happen BEFORE clinical filtering. Let me fix this.

Actually, looking at the existing code structure, I need to insert hierarchy validation AFTER converting to objects but BEFORE clinical filtering. Let me revise:

```python
def validate_and_convert_annotations(
    raw_data: dict[str, Any],
    doc_text: str,
    doc_id: str,
    threshold: int = 90,
) -> AnnotationFile:
    # ... (existing span validation through line 409)

    # ... (existing reasoning step conversion through line 409)

    # ... (existing document annotation conversion through line 443)

    # ... (existing validation complete logging line 445-448)

    # ===== HIERARCHY VALIDATION (NEW - insert here, before clinical filtering) =====

    # Stage 1: Filter reasoning steps with no spans
    hierarchy_valid_steps = []
    filtered_steps_no_spans = 0

    for step in reasoning_steps:
        if len(step.span_ids) == 0:
            filtered_steps_no_spans += 1
            logger.info(f"Hierarchy: filtered reasoning step with no spans: {step.concept.display}")
        else:
            hierarchy_valid_steps.append(step)

    # Update for next validation stages
    reasoning_steps = hierarchy_valid_steps

    # ===== END HIERARCHY VALIDATION =====

    # ... (continue with existing clinical filtering code)
```

**Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_llm.py::test_filter_reasoning_step_no_spans -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_llm.py src/textractor/api/llm.py
git commit -m "feat: filter reasoning steps with no spans (Issue #50)"
```

---

## Task 2: Write Test for Document Annotation Filtering (No Reasoning Steps)

**Files:**
- Modify: `tests/test_llm.py` (add new test)

**Step 1: Write failing test**

Add this test to `tests/test_llm.py`:

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

    # Reasoning step and span should be kept but will be removed by clinical filtering (orphaned)
    # Just verify annotation was filtered
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_llm.py::test_filter_document_annotation_no_steps -v
```

Expected: FAIL (will keep the document annotation)

**Step 3: Implement document annotation filtering - no reasoning steps**

In `src/textractor/api/llm.py`, in the hierarchy validation section (after Stage 1), add Stage 2:

```python
    # ===== HIERARCHY VALIDATION =====

    # Stage 1: Filter reasoning steps with no spans
    hierarchy_valid_steps = []
    filtered_steps_no_spans = 0

    for step in reasoning_steps:
        if len(step.span_ids) == 0:
            filtered_steps_no_spans += 1
            logger.info(f"Hierarchy: filtered reasoning step with no spans: {step.concept.display}")
        else:
            hierarchy_valid_steps.append(step)

    reasoning_steps = hierarchy_valid_steps

    # Stage 2: Filter document annotations with no reasoning steps or direct span links
    hierarchy_valid_anns = []
    filtered_anns_no_steps = 0
    filtered_anns_direct_spans = 0

    for ann in document_annotations:
        # Check for direct span links (should be empty for AI)
        if len(ann.evidence_span_ids) > 0:
            filtered_anns_direct_spans += 1
            logger.info(f"Hierarchy: filtered annotation with direct span links: {ann.concept.display}")
            continue

        # Check for reasoning step requirement
        if len(ann.reasoning_step_ids) == 0:
            filtered_anns_no_steps += 1
            logger.info(f"Hierarchy: filtered annotation with no reasoning steps: {ann.concept.display}")
            continue

        hierarchy_valid_anns.append(ann)

    document_annotations = hierarchy_valid_anns

    # Log hierarchy validation summary
    if filtered_steps_no_spans > 0 or filtered_anns_no_steps > 0 or filtered_anns_direct_spans > 0:
        logger.info(
            f"Hierarchy validation: filtered {filtered_steps_no_spans} reasoning steps (no spans), "
            f"{filtered_anns_no_steps} document annotations (no reasoning steps), "
            f"{filtered_anns_direct_spans} document annotations (direct span links)"
        )

    # ===== END HIERARCHY VALIDATION =====

    # ... (continue with existing clinical filtering)
```

**Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_llm.py::test_filter_document_annotation_no_steps -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_llm.py src/textractor/api/llm.py
git commit -m "feat: filter document annotations with no reasoning steps (Issue #50)"
```

---

## Task 3: Write Test for Document Annotation Filtering (Direct Span Links)

**Files:**
- Modify: `tests/test_llm.py` (add new test)

**Step 1: Write failing test**

Add this test to `tests/test_llm.py`:

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

    doc_text = "chest pain"
    result = validate_and_convert_annotations(raw_data, doc_text, "test_doc")

    # Document annotation should be filtered (has direct span links)
    assert len(result.document_annotations) == 0
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_llm.py::test_filter_document_annotation_direct_spans -v
```

Expected: PASS (already implemented in Task 2 Stage 2)

**Step 3: Verify implementation already exists**

The code from Task 2 already handles this case:

```python
# Check for direct span links (should be empty for AI)
if len(ann.evidence_span_ids) > 0:
    filtered_anns_direct_spans += 1
    logger.info(f"Hierarchy: filtered annotation with direct span links: {ann.concept.display}")
    continue
```

No additional code needed.

**Step 4: Run test to confirm it passes**

Run:
```bash
uv run pytest tests/test_llm.py::test_filter_document_annotation_direct_spans -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_llm.py
git commit -m "test: add test for filtering direct span links (Issue #50)"
```

---

## Task 4: Write Test for Valid Hierarchy Passes Through

**Files:**
- Modify: `tests/test_llm.py` (add new test)

**Step 1: Write passing test**

Add this test to `tests/test_llm.py`:

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
                "evidence_span_indices": [],  # Valid - no direct links
                "reasoning_step_indices": [0],  # Valid - has reasoning step
                "category": "symptom",
            },
        ],
    }

    doc_text = "chest pain"
    result = validate_and_convert_annotations(raw_data, doc_text, "test_doc")

    # All should pass through hierarchy and clinical filtering
    assert len(result.spans) == 1
    assert len(result.reasoning_steps) == 1
    assert len(result.document_annotations) == 1
    assert result.document_annotations[0].concept.display == "Chest pain"
```

**Step 2: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_llm.py::test_valid_hierarchy_passes -v
```

Expected: PASS (no filtering should occur)

**Step 3: Commit**

```bash
git add tests/test_llm.py
git commit -m "test: add test for valid hierarchy passing through (Issue #50)"
```

---

## Task 5: Write Test for Cascade Filtering

**Files:**
- Modify: `tests/test_llm.py` (add new test)

**Step 1: Write test**

Add this test to `tests/test_llm.py`:

```python
def test_cascade_filter_all_steps_invalid():
    """Test that all annotations are filtered when all reasoning steps have no spans."""
    from textractor.api.llm import validate_and_convert_annotations

    raw_data = {
        "spans": [{"start": 0, "end": 10, "text": "chest pain"}],
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
                "evidence_span_indices": [],
                "reasoning_step_indices": [0],
                "category": "symptom",
            },
        ],
    }

    doc_text = "chest pain"
    result = validate_and_convert_annotations(raw_data, doc_text, "test_doc")

    # Reasoning step filtered (no spans) -> document annotation references invalid step -> clinical filter removes it
    assert len(result.reasoning_steps) == 0

    # Clinical filtering will cascade remove the document annotation (orphaned)
    # and the span (orphaned)
    assert len(result.document_annotations) == 0
    assert len(result.spans) == 0
```

**Step 2: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_llm.py::test_cascade_filter_all_steps_invalid -v
```

Expected: PASS (hierarchy + clinical filtering work together)

**Step 3: Commit**

```bash
git add tests/test_llm.py
git commit -m "test: add cascade filtering test (Issue #50)"
```

---

## Task 6: Update LLM Tool Schema - Remove evidence_span_indices

**Files:**
- Modify: `src/textractor/api/llm.py:~165-200` (generate_annotations_raw function)

**Step 1: Remove evidence_span_indices from schema**

In `src/textractor/api/llm.py`, find the `generate_annotations_raw()` function. Update the `document_annotations` schema (around line 165-200):

Find this section:
```python
"document_annotations": {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "concept_code": {"type": "string"},
            "concept_display": {"type": "string"},
            "evidence_span_indices": {"type": "array", "items": {"type": "integer"}},  # REMOVE THIS
            "reasoning_step_indices": {"type": "array", "items": {"type": "integer"}},
            "note": {"type": "string"},
            "category": {...}
        },
        "required": ["concept_code", "concept_display", "category"]
    }
}
```

Replace with:
```python
"document_annotations": {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "concept_code": {"type": "string"},
            "concept_display": {"type": "string"},
            # evidence_span_indices REMOVED - no direct span links
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

**Step 2: Verify schema compiles**

Run:
```bash
uv run python -c "from textractor.api.llm import generate_annotations_raw; print('OK')"
```

Expected: `OK` (no syntax errors)

**Step 3: Commit**

```bash
git add src/textractor/api/llm.py
git commit -m "feat: remove evidence_span_indices from LLM schema (Issue #50)"
```

---

## Task 7: Update LLM Tool Schema - Add minItems to span_indices

**Files:**
- Modify: `src/textractor/api/llm.py:~145-165` (reasoning_steps schema)

**Step 1: Add minItems constraint to reasoning steps**

In `src/textractor/api/llm.py`, find the `reasoning_steps` schema (around line 145-165):

Find this section:
```python
"reasoning_steps": {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "concept_code": {"type": "string"},
            "concept_display": {"type": "string"},
            "span_indices": {"type": "array", "items": {"type": "integer"}},  # ADD minItems here
            "note": {"type": "string"}
        },
        "required": ["concept_code", "concept_display", "span_indices"]
    }
}
```

Replace with:
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

**Step 2: Verify schema compiles**

Run:
```bash
uv run python -c "from textractor.api.llm import generate_annotations_raw; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add src/textractor/api/llm.py
git commit -m "feat: add minItems constraint to span_indices (Issue #50)"
```

---

## Task 8: Update LLM Prompt with Hierarchy Instructions

**Files:**
- Modify: `src/textractor/api/llm.py:~208-234` (prompt in generate_annotations_raw)

**Step 1: Add hierarchy instruction to prompt**

In `src/textractor/api/llm.py`, find the prompt in `generate_annotations_raw()` (around line 208):

Find the Instructions section and add a new instruction #5 about hierarchy:

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

Note: The numbering shifts - the existing category instruction becomes #7, and "Be accurate" becomes #8.

**Step 2: Verify prompt compiles**

Run:
```bash
uv run python -c "from textractor.api.llm import generate_annotations_raw; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add src/textractor/api/llm.py
git commit -m "feat: add hierarchy instructions to LLM prompt (Issue #50)"
```

---

## Task 9: Run All Tests

**Files:**
- N/A (verification)

**Step 1: Run all llm tests**

Run:
```bash
uv run pytest tests/test_llm.py -v
```

Expected: All tests PASS including new hierarchy tests

**Step 2: Run all tests**

Run:
```bash
uv run pytest -v
```

Expected: All tests PASS (no regressions)

**Step 3: Check for any failures**

If failures occur:
- Review test output
- Fix any issues
- Re-run tests

Expected: All tests passing

---

## Task 10: Manual Integration Test

**Files:**
- N/A (manual testing)

**Step 1: Start backend server**

Run in terminal 1:
```bash
TEXTRACTOR_DOC_ROOT=./data/documents uv run textractor
```

Expected: Server starts on port 8000

**Step 2: Start frontend dev server**

Run in terminal 2:
```bash
cd frontend && npm run dev
```

Expected: Vite starts on port 5173

**Step 3: Test pre-annotation with hierarchy**

1. Open browser to `http://localhost:5173`
2. Create/open a document with text: "Patient has chest pain and fever"
3. Click "✨ Pre-annotate" button
4. Check backend logs for hierarchy validation output
5. Expected log output:
   ```
   Hierarchy validation: filtered 0 reasoning steps (no spans), 0 document annotations (no reasoning steps), 0 document annotations (direct span links)
   ```
   (No filtering for valid hierarchy)

**Step 4: Check annotation graph**

1. Switch to "Annotation Graph" tab
2. Verify graph shows clean hierarchy:
   - Spans at bottom
   - Reasoning Steps in middle
   - Document Annotations at top
   - Edges: Document → Reasoning Step → Span
   - NO direct edges from Document to Span

**Step 5: Check saved JSON**

Open `data/documents/<doc_id>.ann.json` and verify:
```json
{
  "document_annotations": [
    {
      "id": "ann_xxx",
      "concept": {...},
      "evidence_span_ids": [],  // EMPTY - no direct span links
      "reasoning_step_ids": ["step_yyy"],  // Has reasoning step
      "category": "symptom",
      "source": "model"
    }
  ],
  "reasoning_steps": [
    {
      "id": "step_yyy",
      "concept": {...},
      "span_ids": ["span_zzz"],  // Has span
      "source": "model"
    }
  ]
}
```

**Step 6: Test with existing human annotations**

1. Load a document with existing human annotations that have direct span links
2. Verify it loads correctly
3. Verify annotation graph shows direct links (allowed for humans)
4. Verify no errors in console

**Step 7: Document test results**

Create a brief test report noting:
- Pre-annotation works with strict hierarchy
- Annotation graph displays correctly
- Saved JSON has empty evidence_span_ids
- Existing human annotations still work

---

## Task 11: Update Documentation

**Files:**
- Modify: `CLAUDE.md` (update pre-annotation section)

**Step 1: Document hierarchy enforcement in CLAUDE.md**

Find the pre-annotation section in `CLAUDE.md` and add:

```markdown
### Hierarchy Enforcement

Pre-annotation enforces strict hierarchical progression:

**Strict hierarchy flow:**
- Spans (text evidence) → Reasoning Steps (intermediate concepts) → Document Annotations (final findings)
- Every reasoning step must reference ≥1 span
- Every document annotation must reference ≥1 reasoning step
- No direct span links from document annotations (evidence_span_ids is empty for AI)

**Validation:**
- LLM tool schema prevents direct span links
- Post-processing filters violations
- Reasoning steps with 0 spans are filtered
- Document annotations with 0 reasoning steps are filtered
- Detailed logging shows what was filtered

**Human flexibility:**
- Hierarchy rules only apply to AI-generated annotations (source='model')
- Human annotations retain full flexibility including direct span links
- Existing annotations with direct links continue to work

Check backend logs for "Hierarchy validation:" output to see filtering statistics.
```

**Step 2: Commit documentation**

```bash
git add CLAUDE.md
git commit -m "docs: document hierarchy enforcement behavior (Issue #50)"
```

---

## Task 12: Final Integration and Cleanup

**Files:**
- N/A (verification and cleanup)

**Step 1: Run all tests one final time**

Run:
```bash
uv run pytest tests/test_llm.py -v
```

Expected: All tests PASS

**Step 2: Check TypeScript compilation**

Run:
```bash
cd frontend && npx tsc --noEmit
```

Expected: No errors (no frontend changes, but verify)

**Step 3: Verify no regressions**

Test existing functionality:
1. Pre-annotate a purely clinical note
2. Verify all annotations appear
3. Check logs show hierarchy validation passed
4. Verify annotation graph looks correct

**Step 4: Create summary commit**

```bash
git add -A
git commit -m "feat: complete hierarchy enforcement for pre-annotations (Issue #50)

- Remove evidence_span_indices from LLM tool schema
- Add minItems constraints for reasoning_step_indices and span_indices
- Add hierarchy validation in post-processing
- Filter reasoning steps with no spans
- Filter document annotations with no reasoning steps or direct span links
- Add comprehensive test coverage
- Update documentation
- Maintain human annotation flexibility

Closes #50"
```

**Step 5: Push to remote**

```bash
git push origin feature/issue-50-hierarchy-enforcement
```

---

## Testing Checklist

- [x] Unit test: Reasoning steps with no spans are filtered
- [x] Unit test: Document annotations with no reasoning steps are filtered
- [x] Unit test: Document annotations with direct span links are filtered
- [x] Unit test: Valid hierarchy passes through without filtering
- [x] Unit test: Cascade filtering when all steps invalid
- [x] Integration test: Manual end-to-end with annotation graph verification
- [x] Integration test: Saved JSON has empty evidence_span_ids
- [x] Regression test: Existing human annotations still work
- [x] Verification: TypeScript compilation passes
- [x] Verification: Backend logs show hierarchy validation statistics

## Success Criteria

- [x] LLM tool schema removes `evidence_span_indices` from document_annotations
- [x] Schema adds `minItems: 1` to `reasoning_step_indices`
- [x] Schema adds `minItems: 1` to `span_indices` in reasoning_steps
- [x] Prompt explains strict hierarchy requirement
- [x] Post-processing validates and filters hierarchy violations
- [x] Reasoning steps with 0 spans are filtered
- [x] Document annotations with 0 reasoning steps are filtered
- [x] Document annotations with direct span links are filtered
- [x] Detailed logging shows filtering statistics
- [x] Human annotations unaffected
- [x] Backward compatible with existing data
- [x] Annotation graph displays clean hierarchy
- [x] Tests cover all validation scenarios

## Files Modified

**Backend:**
- `src/textractor/api/llm.py` - Schema updates, prompt updates, hierarchy validation

**Tests:**
- `tests/test_llm.py` - Unit tests for hierarchy validation

**Documentation:**
- `CLAUDE.md` - Document hierarchy enforcement

## Rollback Plan

If issues arise:

1. Revert all commits from this feature:
   ```bash
   git revert <commit-range>
   ```

2. No data migration needed - `evidence_span_ids` field still exists in model

3. Frontend has no changes, so no frontend rollback needed

4. Existing annotations continue to work (backward compatible)
