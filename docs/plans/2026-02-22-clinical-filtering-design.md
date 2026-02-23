# Clinical Annotation Filtering Design

**Issue:** [#49](https://github.com/schorndorfer/textractor/issues/49)
**Date:** 2026-02-22
**Status:** Approved

## Overview

Filter AI-generated document annotations to only clinical concepts, preventing demographic and administrative information from being saved as document-level annotations.

## Requirements

**Goal:** Restrict pre-annotations to clinical domain concepts only.

**Scope:**
- Filter at the **Document Annotation** level only
- Keep clinical categories: `problem`, `procedure`, `medication`, `lab`, `symptom`, `diagnosis`, `finding`, `sign`, `device`, `allergy`
- Remove non-clinical categories: `demographic`, `administrative`, `temporal`, `social_history`, `other`
- Cascade cleanup: Remove orphaned reasoning steps and spans that aren't referenced by any clinical document annotation
- Log filtering statistics for observability

**User Intent:**
> "I'm only interested in annotations that feed up to clinical concepts, such as problem, procedure, medication, lab, or symptom. Not stuff like '68 year old male', etc."

**Success Criteria:**
1. LLM categorizes each document annotation during generation
2. Non-clinical annotations are filtered out during post-processing
3. Orphaned reasoning steps and spans are removed
4. Detailed logging shows what was filtered and why
5. Backward compatible - existing annotations without category field still work

## Architecture

### Approach: LLM Categorization with Post-Processing Filter

**Why this approach:**
- LLM already understands clinical context, so categorization is accurate
- Post-processing filter provides control and debugging visibility
- Easy to adjust category allowlist without re-prompting
- Logging helps validate filtering behavior with real data

**Pipeline flow:**

```
extract_medical_terms()
    ↓
search SNOMED for each term
    ↓
generate_annotations_raw() → LLM adds category to each document annotation
    ↓
validate_and_convert_annotations()
    ↓
Filter Stage 1: Remove non-clinical document annotations
    ↓
Filter Stage 2: Remove orphaned reasoning steps
    ↓
Filter Stage 3: Remove orphaned spans
    ↓
Return filtered AnnotationFile
```

## Data Model Changes

### DocumentAnnotation Model

**File:** `src/textractor/api/models.py`

```python
class DocumentAnnotation(BaseModel):
    id: str = Field(default_factory=lambda: f"ann_{uuid4().hex[:8]}")
    concept: Concept
    evidence_span_ids: list[str] = Field(default_factory=list)
    reasoning_step_ids: list[str] = Field(default_factory=list)
    note: str = ""
    source: Literal["human", "model"] = "human"
    category: Optional[str] = None  # NEW: clinical category
```

**Why Optional:**
- Backward compatibility - existing `.ann.json` files don't have this field
- Human-created annotations don't need categories (only AI-generated ones)
- Frontend doesn't need to handle categories (purely backend filtering)

### Clinical Category Constants

**File:** `src/textractor/api/llm.py`

```python
# Clinical categories to keep
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
    "allergy"
}
```

**All categories (for LLM enum):**
- **Clinical:** `problem`, `procedure`, `medication`, `lab`, `symptom`, `diagnosis`, `finding`, `sign`, `device`, `allergy`
- **Non-clinical:** `demographic`, `administrative`, `temporal`, `social_history`, `other`

## LLM Tool Schema Changes

### Update generate_annotations_raw()

**File:** `src/textractor/api/llm.py` (lines ~165-180)

**Add category to document_annotations schema:**

```python
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
            "category": {  # NEW
                "type": "string",
                "enum": [
                    "problem", "procedure", "medication", "lab", "symptom",
                    "diagnosis", "finding", "sign", "device", "allergy",
                    "demographic", "administrative", "temporal",
                    "social_history", "other"
                ]
            }
        },
        "required": ["concept_code", "concept_display", "category"]  # category now required
    }
}
```

### Update Prompt Instructions

**File:** `src/textractor/api/llm.py` (lines ~185-202)

**Add category guidance to existing prompt:**

```
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
```

This ensures Claude categorizes every document annotation during generation.

## Filtering Logic

### Three-Stage Filtering in validate_and_convert_annotations()

**File:** `src/textractor/api/llm.py` (after line 406, before return statement)

**Stage 1: Filter non-clinical document annotations**

```python
# Filter to clinical categories only
clinical_annotations = []
filtered_count = 0
filtered_by_category = {}

for ann in document_annotations:
    category = ann.category or "unknown"
    if category in CLINICAL_CATEGORIES:
        clinical_annotations.append(ann)
    else:
        filtered_count += 1
        filtered_by_category[category] = filtered_by_category.get(category, 0) + 1
        logger.info(f"Filtered out {category} annotation: {ann.concept.display}")
```

**Stage 2: Remove orphaned reasoning steps**

```python
# Find which reasoning steps are referenced by clinical annotations
referenced_step_ids = set()
for ann in clinical_annotations:
    referenced_step_ids.update(ann.reasoning_step_ids)

# Keep only referenced reasoning steps
clinical_steps = [step for step in reasoning_steps if step.id in referenced_step_ids]
orphaned_steps = len(reasoning_steps) - len(clinical_steps)
```

**Stage 3: Remove orphaned spans**

```python
# Find which spans are referenced by clinical reasoning steps
referenced_span_ids = set()
for step in clinical_steps:
    referenced_span_ids.update(step.span_ids)

# Keep only referenced spans
clinical_spans = [span for span in spans if span.id in referenced_span_ids]
orphaned_spans = len(spans) - len(clinical_spans)
```

**Logging Summary:**

```python
if filtered_count > 0:
    logger.info(
        f"Clinical filtering: kept {len(clinical_annotations)}/{len(document_annotations)} annotations, "
        f"removed {filtered_count} non-clinical ({', '.join(f'{cat}={count}' for cat, count in filtered_by_category.items())}), "
        f"cascaded removal: {orphaned_steps} reasoning steps, {orphaned_spans} spans"
    )
```

**Final Return:**

```python
return AnnotationFile(
    doc_id=doc_id,
    spans=clinical_spans,  # Filtered
    reasoning_steps=clinical_steps,  # Filtered
    document_annotations=clinical_annotations,  # Filtered
    completed=False,
)
```

## Error Handling & Edge Cases

### Edge Case 1: All annotations filtered out

**Scenario:** LLM only generates non-clinical annotations (e.g., demographic info only)

**Behavior:**
- Return valid empty AnnotationFile (0 spans, 0 steps, 0 annotations)
- Log warning: "All document annotations were filtered out - no clinical concepts found"
- User sees: No AI annotations appear in UI, can manually annotate

### Edge Case 2: Invalid category

**Scenario:** LLM returns category not in allowed enum (typo or unexpected value)

**Behavior:**
- Treat as non-clinical and filter out
- Log warning: "Unexpected category '{category}' for annotation '{display}' - filtering out"

### Edge Case 3: Missing category

**Scenario:** LLM doesn't provide category field (shouldn't happen with `required` field)

**Behavior:**
- Fallback: Treat as `category="unknown"` and filter out
- Defensive handling ensures system doesn't break

### Edge Case 4: Partial cascade deletion

**Scenario:** Clinical annotation references both clinical and non-clinical reasoning steps

**Behavior:**
- Keep ALL referenced reasoning steps (don't filter steps by category)
- Rationale: If a clinical annotation needs it, keep it regardless of intermediate categorization
- Only document annotations are categorized and filtered

### Backward Compatibility

**Existing `.ann.json` files:**
- Load successfully (category field is Optional)
- No migration needed

**Human-created annotations:**
- No category needed (only applies to AI-generated with source='model')
- Category remains None for human annotations

**Frontend:**
- No changes required
- Category field is backend-only filtering metadata

### Logging Levels

```python
logger.info()    # Summary statistics (counts, totals, filtering results)
logger.info()    # Individual filtered annotations (for debugging)
logger.warning() # Unexpected categories, all annotations filtered, empty results
```

## Testing Strategy

### Unit Tests

**File:** `tests/test_llm.py`

**Test 1: Category filtering logic**
- Mock LLM response with mixed clinical/non-clinical annotations
- Categories: 2 problems, 1 medication, 1 demographic, 1 administrative
- Expected: Keep 3 clinical, filter 2 non-clinical
- Verify filtering statistics dict is correct

**Test 2: Cascade deletion**
- Mock response where non-clinical annotation references reasoning steps/spans
- Clinical annotation references different steps/spans
- Expected: Only clinical annotation and its referenced steps/spans remain
- Verify orphaned steps/spans are removed

**Test 3: All filtered edge case**
- Mock response with only demographic/administrative annotations
- Expected: Empty AnnotationFile ([], [], [])
- Verify warning logged

**Test 4: Invalid category**
- Mock response with category not in enum (e.g., "unknown_type")
- Expected: Filtered out, warning logged

**Test 5: Missing category**
- Mock response where category field is absent
- Expected: Treated as "unknown", filtered out

**Test 6: Backward compatibility**
- Create DocumentAnnotation without category field
- Expected: Loads successfully, category=None

### Integration Tests

**File:** `tests/test_preannotate.py` (new file)

**Test 1: End-to-end filtering**
- Sample note: "68 year old male with chest pain and fever"
- Expected LLM output:
  - "68 year old male" → demographic (filtered)
  - "chest pain" → symptom (kept)
  - "fever" → symptom (kept)
- Verify only clinical annotations returned
- Check log contains filtering statistics

**Test 2: Empty result scenario**
- Sample note: "Patient is a 45 year old female seen in clinic today"
- Only demographic/administrative info
- Expected: Empty AnnotationFile
- Verify warning logged

**Test 3: All clinical scenario**
- Sample note with only clinical content
- Expected: All annotations kept, no filtering
- Verify log shows "kept X/X annotations"

### Manual Testing Checklist

1. Upload note with demographic info ("68 year old male")
2. Click Pre-annotate button
3. Check backend logs for filtering statistics:
   ```
   Clinical filtering: kept 5/7 annotations, removed 2 non-clinical (demographic=1, administrative=1), cascaded removal: 2 reasoning steps, 1 spans
   ```
4. Verify in UI:
   - Demographic annotations don't appear
   - Clinical annotations (problems, symptoms, etc.) do appear
   - AI badges (✨) show on model-generated annotations
5. Check browser console - no errors
6. Verify annotations are marked `source='model'` and `category='problem'` etc in saved JSON

## Files to Modify

**Backend:**
- `src/textractor/api/models.py` - Add optional `category` field to DocumentAnnotation
- `src/textractor/api/llm.py` - Add CLINICAL_CATEGORIES constant, update tool schema, update prompt, add filtering logic

**Tests:**
- `tests/test_llm.py` - Add unit tests for filtering logic
- `tests/test_preannotate.py` - Add integration tests (new file)

**No frontend changes needed** - category is backend-only filtering.

## Implementation Notes

**Where filtering happens:**
- `validate_and_convert_annotations()` in `llm.py` (after span validation, before return)

**Filter order:**
1. Filter document annotations by category
2. Remove orphaned reasoning steps
3. Remove orphaned spans
4. Log statistics

**Category list location:**
- Hardcoded constant in `llm.py` for now
- Can be moved to environment variable later if needed (TEXTRACTOR_CLINICAL_CATEGORIES)

**Logging verbosity:**
- Info level for summary statistics
- Info level for individual filtered items (helps debugging)
- Warning level for edge cases (all filtered, invalid category)

## Future Enhancements

**Potential improvements (not in scope):**

1. **Configurable categories:** Environment variable to customize allowlist without code changes
2. **Category statistics endpoint:** API endpoint to show category distribution for a document
3. **Frontend category display:** Show category badges in UI for debugging
4. **Category-based filtering UI:** Let users toggle which categories to show/hide
5. **Category confidence scores:** Have LLM provide confidence for categorization
6. **Multi-category support:** Allow annotations to have multiple categories

## Success Criteria

1. ✅ DocumentAnnotation model has optional `category` field
2. ✅ LLM tool schema requires category for each document annotation
3. ✅ Prompt instructs Claude on how to categorize
4. ✅ Post-processing filters non-clinical annotations
5. ✅ Orphaned reasoning steps and spans are removed
6. ✅ Detailed logging shows filtering statistics
7. ✅ Backward compatible with existing annotations
8. ✅ Unit and integration tests cover filtering logic
9. ✅ Manual testing validates demographic info is filtered
10. ✅ Clinical annotations (problems, procedures, etc.) are preserved
