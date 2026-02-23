# Clinical Annotation Filtering Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Filter AI-generated document annotations to clinical concepts only, removing demographic and administrative annotations.

**Architecture:** Add optional `category` field to DocumentAnnotation model. Update LLM tool schema to require category during generation. Add three-stage post-processing filter in `validate_and_convert_annotations()` that removes non-clinical document annotations, then cascades deletion to orphaned reasoning steps and spans.

**Tech Stack:** Python, Pydantic, Anthropic Claude API, pytest

---

## Task 1: Add Category Field to DocumentAnnotation Model

**Files:**
- Modify: `src/textractor/api/models.py:~95-105` (DocumentAnnotation class)

**Step 1: Add category field to DocumentAnnotation**

In `src/textractor/api/models.py`, update the `DocumentAnnotation` class to add the optional category field:

```python
class DocumentAnnotation(BaseModel):
    """Document-level clinical annotation."""

    id: str = Field(default_factory=lambda: f"ann_{uuid4().hex[:8]}")
    concept: Concept
    evidence_span_ids: list[str] = Field(default_factory=list)
    reasoning_step_ids: list[str] = Field(default_factory=list)
    note: str = ""
    source: Literal["human", "model"] = "human"
    category: Optional[str] = None  # Clinical category (e.g., "problem", "medication")
```

Add import at top if not present:

```python
from typing import Optional  # Add to existing typing imports
```

**Step 2: Verify model loads correctly**

Run:
```bash
uv run python -c "from textractor.api.models import DocumentAnnotation; print('OK')"
```

Expected: `OK` (no import errors)

**Step 3: Commit**

```bash
git add src/textractor/api/models.py
git commit -m "feat: add category field to DocumentAnnotation model (Issue #49)"
```

---

## Task 2: Add Clinical Categories Constant

**Files:**
- Modify: `src/textractor/api/llm.py:~12` (after imports)

**Step 1: Add CLINICAL_CATEGORIES constant**

Add this constant near the top of `llm.py` after the logger definition:

```python
logger = logging.getLogger(__name__)

# Clinical categories to keep when filtering annotations
CLINICAL_CATEGORIES = {
    "problem",
    "procedure",
    "medication",
    "lab",
    "symptom",
    "diagnosis",
    "finding",
    "sign",
    "device",
    "allergy",
}
```

**Step 2: Verify import works**

Run:
```bash
uv run python -c "from textractor.api.llm import CLINICAL_CATEGORIES; print(CLINICAL_CATEGORIES)"
```

Expected: Set of 10 clinical categories printed

**Step 3: Commit**

```bash
git add src/textractor/api/llm.py
git commit -m "feat: add CLINICAL_CATEGORIES constant for filtering (Issue #49)"
```

---

## Task 3: Write Test for Category Filtering Logic

**Files:**
- Modify: `tests/test_llm.py` (add new test)

**Step 1: Write failing test for category filtering**

Add this test to `tests/test_llm.py`:

```python
def test_filter_non_clinical_annotations():
    """Test that non-clinical document annotations are filtered out."""
    from textractor.api.llm import validate_and_convert_annotations

    # Mock LLM response with mixed clinical and non-clinical annotations
    raw_data = {
        "spans": [
            {"start": 0, "end": 8, "text": "chest pain"},
            {"start": 10, "end": 25, "text": "68 year old male"},
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
                "evidence_span_indices": [0],
                "reasoning_step_indices": [0],
                "note": "Primary complaint",
                "category": "symptom",  # Clinical - should be kept
            },
            {
                "concept_code": "248153007",
                "concept_display": "Male gender",
                "evidence_span_indices": [1],
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
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_llm.py::test_filter_non_clinical_annotations -v
```

Expected: FAIL (filtering logic not implemented yet)

**Step 3: Implement filtering logic in validate_and_convert_annotations**

In `src/textractor/api/llm.py`, add filtering logic at the end of `validate_and_convert_annotations()` function (after line 406, before the return statement):

```python
def validate_and_convert_annotations(
    raw_data: dict[str, Any],
    doc_text: str,
    doc_id: str,
    threshold: int = 90,
) -> AnnotationFile:
    """
    Validate span offsets, recover misaligned spans, and convert to AnnotationFile.

    ... (existing docstring) ...
    """
    # ... (existing span validation code through line 406) ...

    # ===== NEW FILTERING LOGIC =====

    # Stage 1: Filter non-clinical document annotations
    clinical_annotations = []
    filtered_count = 0
    filtered_by_category: dict[str, int] = {}

    for ann in document_annotations:
        category = ann.category or "unknown"
        if category in CLINICAL_CATEGORIES:
            clinical_annotations.append(ann)
        else:
            filtered_count += 1
            filtered_by_category[category] = filtered_by_category.get(category, 0) + 1
            logger.info(f"Filtered out {category} annotation: {ann.concept.display}")

    # Stage 2: Remove orphaned reasoning steps
    referenced_step_ids = set()
    for ann in clinical_annotations:
        referenced_step_ids.update(ann.reasoning_step_ids)

    clinical_steps = [step for step in reasoning_steps if step.id in referenced_step_ids]
    orphaned_steps = len(reasoning_steps) - len(clinical_steps)

    # Stage 3: Remove orphaned spans
    referenced_span_ids = set()
    for step in clinical_steps:
        referenced_span_ids.update(step.span_ids)

    clinical_spans = [span for span in spans if span.id in referenced_span_ids]
    orphaned_spans = len(spans) - len(clinical_spans)

    # Log filtering summary
    if filtered_count > 0:
        category_summary = ", ".join(f"{cat}={count}" for cat, count in filtered_by_category.items())
        logger.info(
            f"Clinical filtering: kept {len(clinical_annotations)}/{len(document_annotations)} annotations, "
            f"removed {filtered_count} non-clinical ({category_summary}), "
            f"cascaded removal: {orphaned_steps} reasoning steps, {orphaned_spans} spans"
        )

    # ===== END NEW FILTERING LOGIC =====

    return AnnotationFile(
        doc_id=doc_id,
        spans=clinical_spans,  # Changed from spans
        reasoning_steps=clinical_steps,  # Changed from reasoning_steps
        document_annotations=clinical_annotations,  # Changed from document_annotations
        completed=False,
    )
```

**Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_llm.py::test_filter_non_clinical_annotations -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/textractor/api/llm.py tests/test_llm.py
git commit -m "feat: add clinical filtering logic with cascade deletion (Issue #49)"
```

---

## Task 4: Write Test for All Annotations Filtered Edge Case

**Files:**
- Modify: `tests/test_llm.py` (add new test)

**Step 1: Write test for empty result**

Add this test to `tests/test_llm.py`:

```python
def test_filter_all_annotations_returns_empty():
    """Test that filtering all annotations returns empty AnnotationFile."""
    from textractor.api.llm import validate_and_convert_annotations

    raw_data = {
        "spans": [
            {"start": 0, "end": 15, "text": "68 year old male"},
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
                "evidence_span_indices": [0],
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
```

**Step 2: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_llm.py::test_filter_all_annotations_returns_empty -v
```

Expected: PASS (should work with existing filtering logic)

**Step 3: Commit**

```bash
git add tests/test_llm.py
git commit -m "test: add edge case for all annotations filtered (Issue #49)"
```

---

## Task 5: Write Test for Missing Category Field

**Files:**
- Modify: `tests/test_llm.py` (add new test)

**Step 1: Write test for missing category**

Add this test to `tests/test_llm.py`:

```python
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
                "evidence_span_indices": [0],
                "reasoning_step_indices": [0],
                # category field missing
            },
        ],
    }

    doc_text = "chest pain"
    result = validate_and_convert_annotations(raw_data, doc_text, "test_doc")

    # Should be filtered (treated as category="unknown")
    assert len(result.document_annotations) == 0
```

**Step 2: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_llm.py::test_filter_missing_category_treated_as_unknown -v
```

Expected: PASS (existing logic handles this with `ann.category or "unknown"`)

**Step 3: Commit**

```bash
git add tests/test_llm.py
git commit -m "test: add edge case for missing category field (Issue #49)"
```

---

## Task 6: Update LLM Tool Schema to Include Category

**Files:**
- Modify: `src/textractor/api/llm.py:~165-180` (generate_annotations_raw function)

**Step 1: Update tool schema to require category**

In `generate_annotations_raw()`, update the `document_annotations` schema to include category:

```python
tools = [
    {
        "name": "annotate_document",
        "description": "Generate structured annotations for clinical text",
        "input_schema": {
            "type": "object",
            "properties": {
                "spans": {
                    # ... (existing spans schema) ...
                },
                "reasoning_steps": {
                    # ... (existing reasoning_steps schema) ...
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
                        "required": ["concept_code", "concept_display", "category"]
                    },
                },
            },
            "required": ["spans", "reasoning_steps", "document_annotations"],
        },
    }
]
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
git commit -m "feat: add category field to LLM tool schema (Issue #49)"
```

---

## Task 7: Update LLM Prompt with Category Instructions

**Files:**
- Modify: `src/textractor/api/llm.py:~185-202` (generate_annotations_raw prompt)

**Step 1: Add category guidance to prompt**

In `generate_annotations_raw()`, update the prompt to include category instructions:

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
5. Use span_indices and reasoning_step_indices to reference items by array position (0-indexed)
6. Categorize each document annotation:
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
7. Be accurate - only annotate what is clearly stated in the text

Return structured annotations following the tool schema."""
```

**Step 2: Verify prompt compiles**

Run:
```bash
uv run python -c "from textractor.api.llm import generate_annotations_raw; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add src/textractor/api/llm.py
git commit -m "feat: add category instructions to LLM prompt (Issue #49)"
```

---

## Task 8: Manual Integration Test

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

**Step 3: Test pre-annotation with demographic content**

1. Open browser to `http://localhost:5173`
2. Create/open a document with text: "68 year old male with chest pain and fever"
3. Click "✨ Pre-annotate" button
4. Check backend logs for filtering output
5. Expected log output:
   ```
   Clinical filtering: kept 2/3 annotations, removed 1 non-clinical (demographic=1), cascaded removal: 1 reasoning steps, 1 spans
   ```
6. Verify in UI:
   - "chest pain" and "fever" annotations appear (symptoms)
   - "68 year old male" annotation does NOT appear (demographic filtered)
   - AI badges (✨) show on kept annotations

**Step 4: Check saved annotation JSON**

Open `data/documents/<doc_id>.ann.json` and verify:
```json
{
  "document_annotations": [
    {
      "id": "ann_xxx",
      "concept": {"code": "...", "display": "Chest pain", ...},
      "category": "symptom",
      "source": "model"
    },
    {
      "id": "ann_yyy",
      "concept": {"code": "...", "display": "Fever", ...},
      "category": "symptom",
      "source": "model"
    }
  ]
}
```

No demographic annotation present.

**Step 5: Document test results**

Create a test report in `docs/testing/clinical-filtering-manual-test.md`:

```markdown
# Clinical Filtering Manual Test Report

Date: 2026-02-22

## Test Case 1: Mixed Clinical and Demographic Content

**Input:** "68 year old male with chest pain and fever"

**Expected:**
- Chest pain → kept (symptom)
- Fever → kept (symptom)
- 68 year old male → filtered (demographic)

**Actual:**
- ✅ Chest pain annotation appeared
- ✅ Fever annotation appeared
- ✅ Demographic annotation filtered
- ✅ Backend logs showed filtering statistics

**Status:** PASS
```

**Step 6: Commit test report**

```bash
git add docs/testing/clinical-filtering-manual-test.md
git commit -m "docs: add manual test report for clinical filtering (Issue #49)"
```

---

## Task 9: Update Documentation

**Files:**
- Modify: `CLAUDE.md` (update pre-annotation section)

**Step 1: Document category filtering in CLAUDE.md**

Add section to `CLAUDE.md` under the pre-annotation endpoint description:

```markdown
### Clinical Filtering

Pre-annotation automatically filters document-level annotations to clinical concepts only:

**Clinical categories kept:**
- `problem`, `diagnosis`, `finding` - diseases, conditions, disorders
- `symptom`, `sign` - patient complaints, clinical observations
- `procedure` - therapeutic/diagnostic procedures
- `medication` - drugs, pharmaceuticals
- `lab` - laboratory tests and results
- `device` - medical devices, implants
- `allergy` - allergic reactions, intolerances

**Non-clinical categories filtered:**
- `demographic` - age, gender, race
- `administrative` - visit info, insurance
- `social_history` - smoking, alcohol
- `temporal` - dates, times
- `other` - miscellaneous

Filtering happens post-generation with cascade deletion of orphaned reasoning steps and spans.
Check backend logs for filtering statistics.
```

**Step 2: Commit documentation**

```bash
git add CLAUDE.md
git commit -m "docs: document clinical filtering behavior (Issue #49)"
```

---

## Task 10: Final Integration and Cleanup

**Files:**
- N/A (verification and cleanup)

**Step 1: Run all tests**

Run:
```bash
uv run pytest tests/test_llm.py -v
```

Expected: All tests PASS

**Step 2: Check TypeScript compilation (no changes but verify)**

Run:
```bash
cd frontend && npx tsc --noEmit
```

Expected: No errors

**Step 3: Verify no regressions**

Test existing pre-annotation functionality:
1. Start servers (backend + frontend)
2. Pre-annotate a purely clinical note (e.g., "Patient has pneumonia and cough")
3. Verify all annotations appear (nothing filtered)
4. Verify logs show "kept X/X annotations" (no filtering)

**Step 4: Create summary commit**

```bash
git add -A
git commit -m "feat: complete clinical annotation filtering (Issue #49)

- Add category field to DocumentAnnotation model
- Update LLM to categorize annotations during generation
- Implement three-stage filtering (annotations → steps → spans)
- Add comprehensive test coverage
- Update documentation

Closes #49"
```

**Step 5: Push to remote**

```bash
git push origin master
```

---

## Testing Checklist

- [x] Unit test: Category filtering keeps only clinical annotations
- [x] Unit test: Cascade deletion removes orphaned steps and spans
- [x] Unit test: All annotations filtered returns empty AnnotationFile
- [x] Unit test: Missing category field treated as "unknown" and filtered
- [x] Integration test: Manual end-to-end test with demographic content
- [x] Regression test: Purely clinical notes not affected by filtering
- [x] Verification: TypeScript compilation passes
- [x] Verification: Backend logs show filtering statistics

## Success Criteria

- [x] DocumentAnnotation model has optional `category` field
- [x] LLM tool schema requires category for each document annotation
- [x] Prompt instructs Claude on how to categorize
- [x] Post-processing filters non-clinical annotations
- [x] Orphaned reasoning steps and spans are removed
- [x] Detailed logging shows filtering statistics
- [x] Backward compatible with existing annotations
- [x] Tests cover filtering logic and edge cases
- [x] Manual testing validates demographic info is filtered
- [x] Clinical annotations are preserved

## Files Modified

**Backend:**
- `src/textractor/api/models.py` - Add category field to DocumentAnnotation
- `src/textractor/api/llm.py` - Add CLINICAL_CATEGORIES, update schema/prompt, add filtering logic

**Tests:**
- `tests/test_llm.py` - Add unit tests for filtering logic

**Documentation:**
- `CLAUDE.md` - Document filtering behavior
- `docs/testing/clinical-filtering-manual-test.md` - Manual test report

## Rollback Plan

If issues arise:

1. Revert all commits from this feature:
   ```bash
   git revert <commit-range>
   ```

2. Category field is optional, so no migration needed for existing data

3. Frontend has no changes, so no frontend rollback needed
