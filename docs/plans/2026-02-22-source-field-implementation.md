# Source Field Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `source` field to annotation models to distinguish between human and model-generated annotations.

**Architecture:** Add `source: Literal['human', 'model']` field to backend Pydantic models with default='human' for backward compatibility. Frontend detects substantive edits and flips source from 'model' to 'human'. Visual badges (✨) indicate model-generated items in UI.

**Tech Stack:** FastAPI, Pydantic, React, TypeScript

---

## Task 1: Backend Model Changes

**Files:**
- Modify: `src/textractor/api/models.py`
- Test: `tests/test_models.py` (create if doesn't exist)

**Step 1: Write test for backward compatibility**

Create `tests/test_models.py`:

```python
import json
from textractor.api.models import Span, ReasoningStep, DocumentAnnotation, AnnotationFile


def test_span_backward_compatibility():
    """Test that spans without source field default to 'human'"""
    data = {"id": "span_abc123", "start": 0, "end": 5, "text": "hello"}
    span = Span.model_validate(data)
    assert span.source == "human"


def test_reasoning_step_backward_compatibility():
    """Test that reasoning steps without source field default to 'human'"""
    data = {
        "id": "step_abc123",
        "concept": {"code": "123", "display": "Test", "system": "SNOMED-CT"},
        "span_ids": [],
        "note": "",
    }
    step = ReasoningStep.model_validate(data)
    assert step.source == "human"


def test_document_annotation_backward_compatibility():
    """Test that document annotations without source field default to 'human'"""
    data = {
        "id": "ann_abc123",
        "concept": {"code": "123", "display": "Test", "system": "SNOMED-CT"},
        "evidence_span_ids": [],
        "reasoning_step_ids": [],
        "note": "",
    }
    ann = DocumentAnnotation.model_validate(data)
    assert ann.source == "human"


def test_annotation_file_with_mixed_sources():
    """Test that annotation files can contain mixed source annotations"""
    data = {
        "doc_id": "doc_001",
        "spans": [
            {"id": "span_1", "start": 0, "end": 5, "text": "hello", "source": "human"},
            {"id": "span_2", "start": 6, "end": 11, "text": "world", "source": "model"},
        ],
        "reasoning_steps": [],
        "document_annotations": [],
    }
    ann_file = AnnotationFile.model_validate(data)
    assert ann_file.spans[0].source == "human"
    assert ann_file.spans[1].source == "model"
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_models.py -v
```

Expected: FAIL - models don't have `source` field yet

**Step 3: Add source field to Span model**

In `src/textractor/api/models.py`, update the Span class:

```python
from typing import Literal

class Span(BaseModel):
    id: str = Field(default_factory=lambda: _uuid("span"))
    start: int
    end: int
    text: str
    source: Literal['human', 'model'] = 'human'
```

**Step 4: Add source field to ReasoningStep model**

In `src/textractor/api/models.py`, update the ReasoningStep class:

```python
class ReasoningStep(BaseModel):
    id: str = Field(default_factory=lambda: _uuid("step"))
    concept: Concept
    span_ids: list[str] = Field(default_factory=list)
    note: str = ""
    source: Literal['human', 'model'] = 'human'
```

**Step 5: Add source field to DocumentAnnotation model**

In `src/textractor/api/models.py`, update the DocumentAnnotation class:

```python
class DocumentAnnotation(BaseModel):
    id: str = Field(default_factory=lambda: _uuid("ann"))
    concept: Concept
    evidence_span_ids: list[str] = Field(default_factory=list)
    reasoning_step_ids: list[str] = Field(default_factory=list)
    note: str = ""
    source: Literal['human', 'model'] = 'human'
```

**Step 6: Add Literal import if not present**

At the top of `src/textractor/api/models.py`, ensure Literal is imported:

```python
from typing import Optional, Literal
```

**Step 7: Run tests to verify they pass**

```bash
uv run pytest tests/test_models.py -v
```

Expected: PASS - all 4 tests passing

**Step 8: Test with actual annotation file**

```bash
uv run python -c "
from pathlib import Path
import json
from textractor.api.models import AnnotationFile

# Load existing annotation file
path = Path('data/documents/note_001.ann.json')
data = json.loads(path.read_text())
ann = AnnotationFile.model_validate(data)

# Verify all items have source='human' by default
print(f'Spans: {[s.source for s in ann.spans]}')
print(f'Steps: {[s.source for s in ann.reasoning_steps]}')
print(f'Annotations: {[a.source for a in ann.document_annotations]}')
"
```

Expected: All outputs show `['human', 'human', ...]`

**Step 9: Commit backend changes**

```bash
git add src/textractor/api/models.py tests/test_models.py
git commit -m "feat: add source field to annotation models (Issue #40)

Add source field with 'human' | 'model' values to Span, ReasoningStep,
and DocumentAnnotation models. Defaults to 'human' for backward compatibility.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: Frontend Type Updates

**Files:**
- Modify: `frontend/src/types/index.ts`

**Step 1: Add source field to Span interface**

In `frontend/src/types/index.ts`:

```typescript
export interface Span {
  id: string;
  start: number;
  end: number;
  text: string;
  source: 'human' | 'model';
}
```

**Step 2: Add source field to ReasoningStep interface**

```typescript
export interface ReasoningStep {
  id: string;
  concept: Concept;
  span_ids: string[];
  note?: string;
  source: 'human' | 'model';
}
```

**Step 3: Add source field to DocumentAnnotation interface**

```typescript
export interface DocumentAnnotation {
  id: string;
  concept: Concept;
  evidence_span_ids: string[];
  reasoning_step_ids: string[];
  note?: string;
  source: 'human' | 'model';
}
```

**Step 4: Verify TypeScript compilation**

```bash
npx --prefix /Users/williamthompson/Code/projects/clinical-entity-extraction/projects/textractor/frontend tsc --noEmit
```

Expected: Compilation errors in components that create entities (missing `source` field)

**Step 5: Note the errors for next tasks**

Expected errors in:
- `DocumentViewer.tsx` (span creation)
- `ReasoningStepList.tsx` (step creation)
- `DocumentAnnotationList.tsx` (annotation creation)

Do NOT commit yet - will fix compilation errors in next tasks.

---

## Task 3: Update Span Creation (DocumentViewer)

**Files:**
- Modify: `frontend/src/components/DocumentViewer.tsx`

**Step 1: Add source field to span creation**

Find the `handleMouseUp` function in `DocumentViewer.tsx`. Update the span creation:

```typescript
const newSpan: Span = {
  id: randomId('span'),
  start,
  end,
  text: selectedText,
  source: 'human',
};
```

**Step 2: Verify TypeScript compilation**

```bash
npx --prefix /Users/williamthompson/Code/projects/clinical-entity-extraction/projects/textractor/frontend tsc --noEmit
```

Expected: DocumentViewer errors gone, but ReasoningStepList and DocumentAnnotationList errors remain

**Step 3: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/components/DocumentViewer.tsx
git commit -m "feat: add source field to Span type and creation (Issue #40)

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: Update ReasoningStep Creation

**Files:**
- Modify: `frontend/src/components/ReasoningStepList.tsx`

**Step 1: Find the addStep function**

Locate the `addStep` function in `ReasoningStepList.tsx`.

**Step 2: Add source field to step creation**

Update the new step object:

```typescript
const addStep = () => {
  if (disabled) return;
  const id = randomId('step');
  const newStep: ReasoningStep = {
    id,
    concept: { code: '', display: '', system: 'SNOMED-CT' },
    span_ids: [],
    note: '',
    source: 'human',
  };
  onChange([...steps, newStep]);
  setEditingId(id);
  setDraftConcept(null);
  setDraftSpanIds([]);
  setDraftNote('');
};
```

**Step 3: Verify TypeScript compilation**

```bash
npx --prefix /Users/williamthompson/Code/projects/clinical-entity-extraction/projects/textractor/frontend tsc --noEmit
```

Expected: ReasoningStepList errors gone, DocumentAnnotationList errors remain

**Step 4: Commit**

```bash
git add frontend/src/components/ReasoningStepList.tsx
git commit -m "feat: add source field to ReasoningStep creation (Issue #40)

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5: Update DocumentAnnotation Creation

**Files:**
- Modify: `frontend/src/components/DocumentAnnotationList.tsx`

**Step 1: Find the addAnnotation function**

Locate the `addAnnotation` function in `DocumentAnnotationList.tsx`.

**Step 2: Add source field to annotation creation**

Update the new annotation object:

```typescript
const addAnnotation = () => {
  if (disabled) return;
  const id = randomId('ann');
  const newAnn: DocumentAnnotation = {
    id,
    concept: { code: '', display: '', system: 'SNOMED-CT' },
    evidence_span_ids: [],
    reasoning_step_ids: [],
    note: '',
    source: 'human',
  };
  onChange([...annotations, newAnn]);
  setEditingId(id);
  setDraftConcept(null);
  setDraftSpanIds([]);
  setDraftStepIds([]);
  setDraftNote('');
};
```

**Step 3: Verify TypeScript compilation**

```bash
npx --prefix /Users/williamthompson/Code/projects/clinical-entity-extraction/projects/textractor/frontend tsc --noEmit
```

Expected: All compilation errors resolved (PASS)

**Step 4: Commit**

```bash
git add frontend/src/components/DocumentAnnotationList.tsx
git commit -m "feat: add source field to DocumentAnnotation creation (Issue #40)

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 6: Add Source Transition Logic (ReasoningStepList)

**Files:**
- Modify: `frontend/src/components/ReasoningStepList.tsx`

**Step 1: Find the commitEdit function**

Locate the `commitEdit` function that saves step edits.

**Step 2: Add source transition logic**

Update `commitEdit` to detect substantive changes and flip source to 'human':

```typescript
const commitEdit = (stepId: string) => {
  if (!draftConcept) return;

  onChange(
    steps.map((s) => {
      if (s.id !== stepId) return s;

      // Check if substantive edit occurred (concept or span_ids changed)
      const conceptChanged =
        s.concept.code !== draftConcept.code ||
        s.concept.display !== draftConcept.display;

      const spanIdsChanged =
        JSON.stringify(s.span_ids.sort()) !== JSON.stringify(draftSpanIds.sort());

      const substantiveEdit = conceptChanged || spanIdsChanged;

      return {
        ...s,
        concept: draftConcept,
        span_ids: draftSpanIds,
        note: draftNote,
        // Flip to 'human' if substantive edit occurred
        source: substantiveEdit ? 'human' : s.source,
      };
    })
  );
  setEditingId(null);
};
```

**Step 3: Verify TypeScript compilation**

```bash
npx --prefix /Users/williamthompson/Code/projects/clinical-entity-extraction/projects/textractor/frontend tsc --noEmit
```

Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/components/ReasoningStepList.tsx
git commit -m "feat: add source transition logic for ReasoningStep (Issue #40)

Automatically flip source from 'model' to 'human' when user makes
substantive edits (concept or span_ids changes). Note edits don't
trigger source change.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 7: Add Source Transition Logic (DocumentAnnotationList)

**Files:**
- Modify: `frontend/src/components/DocumentAnnotationList.tsx`

**Step 1: Find the commitEdit function**

Locate the `commitEdit` function that saves annotation edits.

**Step 2: Add source transition logic**

Update `commitEdit` to detect substantive changes:

```typescript
const commitEdit = (annId: string) => {
  if (!draftConcept) return;

  onChange(
    annotations.map((a) => {
      if (a.id !== annId) return a;

      // Check if substantive edit occurred
      const conceptChanged =
        a.concept.code !== draftConcept.code ||
        a.concept.display !== draftConcept.display;

      const evidenceChanged =
        JSON.stringify(a.evidence_span_ids.sort()) !== JSON.stringify(draftSpanIds.sort());

      const stepsChanged =
        JSON.stringify(a.reasoning_step_ids.sort()) !== JSON.stringify(draftStepIds.sort());

      const substantiveEdit = conceptChanged || evidenceChanged || stepsChanged;

      return {
        ...a,
        concept: draftConcept,
        evidence_span_ids: draftSpanIds,
        reasoning_step_ids: draftStepIds,
        note: draftNote,
        // Flip to 'human' if substantive edit occurred
        source: substantiveEdit ? 'human' : a.source,
      };
    })
  );
  setEditingId(null);
};
```

**Step 3: Verify TypeScript compilation**

```bash
npx --prefix /Users/williamthompson/Code/projects/clinical-entity-extraction/projects/textractor/frontend tsc --noEmit
```

Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/components/DocumentAnnotationList.tsx
git commit -m "feat: add source transition logic for DocumentAnnotation (Issue #40)

Automatically flip source from 'model' to 'human' when user makes
substantive edits (concept, evidence_span_ids, or reasoning_step_ids
changes). Note edits don't trigger source change.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 8: Add Visual Badge (ReasoningStepList)

**Files:**
- Modify: `frontend/src/components/ReasoningStepList.tsx`

**Step 1: Find the step item rendering**

Locate where each step is rendered in the return statement (likely in a `.map()` call).

**Step 2: Add AI badge before concept display**

Add badge rendering for model-generated steps:

```typescript
{step.source === 'model' && (
  <span className="ai-badge" title="Model-generated">
    ✨
  </span>
)}
```

Place this immediately before the concept display text. Example context:

```typescript
<div className="step-concept">
  {step.source === 'model' && (
    <span className="ai-badge" title="Model-generated">
      ✨
    </span>
  )}
  {step.concept.display || <em>Select a concept</em>}
</div>
```

**Step 3: Verify compilation**

```bash
npx --prefix /Users/williamthompson/Code/projects/clinical-entity-extraction/projects/textractor/frontend tsc --noEmit
```

Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/components/ReasoningStepList.tsx
git commit -m "feat: add AI badge to model-generated ReasoningSteps (Issue #40)

Display ✨ badge for steps with source='model'.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 9: Add Visual Badge (DocumentAnnotationList)

**Files:**
- Modify: `frontend/src/components/DocumentAnnotationList.tsx`

**Step 1: Find the annotation item rendering**

Locate where each annotation is rendered in the return statement.

**Step 2: Add AI badge before concept display**

Add badge rendering for model-generated annotations:

```typescript
{ann.source === 'model' && (
  <span className="ai-badge" title="Model-generated">
    ✨
  </span>
)}
```

Place this immediately before the concept display text. Example context:

```typescript
<div className="annotation-concept">
  {ann.source === 'model' && (
    <span className="ai-badge" title="Model-generated">
      ✨
    </span>
  )}
  {ann.concept.display || <em>Select a concept</em>}
</div>
```

**Step 3: Verify compilation**

```bash
npx --prefix /Users/williamthompson/Code/projects/clinical-entity-extraction/projects/textractor/frontend tsc --noEmit
```

Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/components/DocumentAnnotationList.tsx
git commit -m "feat: add AI badge to model-generated DocumentAnnotations (Issue #40)

Display ✨ badge for annotations with source='model'.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 10: Add Visual Badge (AnnotationGraph)

**Files:**
- Modify: `frontend/src/components/AnnotationGraph.tsx`

**Step 1: Read the current AnnotationGraph component**

```bash
cat frontend/src/components/AnnotationGraph.tsx | head -100
```

Understand the node rendering structure.

**Step 2: Find node label rendering**

Locate where node labels are created (likely in a `nodes` array construction with React Flow).

**Step 3: Add badge to node labels**

Update node label rendering to include badge for model-generated items. Example:

```typescript
const nodes = [
  ...annotations.document_annotations.map((ann) => ({
    id: ann.id,
    data: {
      label: (
        <>
          {ann.source === 'model' && (
            <span className="ai-badge" title="Model-generated">
              ✨
            </span>
          )}
          {ann.concept.display}
        </>
      ),
    },
    // ... other node properties
  })),
  ...annotations.reasoning_steps.map((step) => ({
    id: step.id,
    data: {
      label: (
        <>
          {step.source === 'model' && (
            <span className="ai-badge" title="Model-generated">
              ✨
            </span>
          )}
          {step.concept.display}
        </>
      ),
    },
    // ... other node properties
  })),
];
```

**Step 4: Verify compilation**

```bash
npx --prefix /Users/williamthompson/Code/projects/clinical-entity-extraction/projects/textractor/frontend tsc --noEmit
```

Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/components/AnnotationGraph.tsx
git commit -m "feat: add AI badge to AnnotationGraph nodes (Issue #40)

Display ✨ badge on graph nodes for model-generated steps and annotations.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 11: Add CSS Styling

**Files:**
- Modify: `frontend/src/App.css` (or appropriate stylesheet)

**Step 1: Add AI badge styles**

Add the following CSS rules:

```css
.ai-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  background: #9333ea;
  border-radius: 50%;
  font-size: 12px;
  margin-right: 6px;
  flex-shrink: 0;
  vertical-align: middle;
}
```

**Step 2: Build frontend to verify styles**

```bash
npm run build --prefix /Users/williamthompson/Code/projects/clinical-entity-extraction/projects/textractor/frontend
```

Expected: Build succeeds

**Step 3: Commit**

```bash
git add frontend/src/App.css
git commit -m "style: add AI badge CSS styling (Issue #40)

Purple circular badge for model-generated annotations.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 12: Manual Testing

**Files:**
- Test: `data/documents/note_001.ann.json` (or create test file)

**Step 1: Start backend**

```bash
TEXTRACTOR_DOC_ROOT=./data/documents uv run textractor
```

**Step 2: Start frontend dev server**

```bash
cd frontend && npm run dev
```

**Step 3: Create test annotation file with model-generated content**

Create `data/documents/test_source.json`:

```json
{
  "id": "test_source",
  "text": "Patient presents with chest pain and shortness of breath.",
  "metadata": {}
}
```

Create `data/documents/test_source.ann.json`:

```json
{
  "doc_id": "test_source",
  "spans": [
    {
      "id": "span_1",
      "start": 22,
      "end": 32,
      "text": "chest pain",
      "source": "model"
    }
  ],
  "reasoning_steps": [
    {
      "id": "step_1",
      "concept": {
        "code": "29857009",
        "display": "Chest pain",
        "system": "SNOMED-CT"
      },
      "span_ids": ["span_1"],
      "note": "",
      "source": "model"
    }
  ],
  "document_annotations": [
    {
      "id": "ann_1",
      "concept": {
        "code": "194828000",
        "display": "Angina",
        "system": "SNOMED-CT"
      },
      "evidence_span_ids": ["span_1"],
      "reasoning_step_ids": ["step_1"],
      "note": "",
      "source": "model"
    }
  ],
  "completed": false
}
```

**Step 4: Test in browser (http://localhost:5173)**

Verify:
- ✅ AI badges (✨) appear next to model-generated step and annotation
- ✅ No badge appears on the span (Spans don't show badges)
- ✅ Edit the reasoning step concept → badge disappears
- ✅ Edit the document annotation concept → badge disappears
- ✅ Edit only the note → badge stays (notes don't trigger source change)
- ✅ Backward compatibility: Open existing documents → all annotations show source='human'
- ✅ AnnotationGraph shows badges on model-generated nodes

**Step 5: Test backend compatibility**

```bash
uv run python -c "
from pathlib import Path
import json
from textractor.api.models import AnnotationFile

# Load test file
path = Path('data/documents/test_source.ann.json')
data = json.loads(path.read_text())
ann = AnnotationFile.model_validate(data)

# Verify sources preserved
print(f'Span source: {ann.spans[0].source}')
print(f'Step source: {ann.reasoning_steps[0].source}')
print(f'Ann source: {ann.document_annotations[0].source}')
"
```

Expected output:
```
Span source: model
Step source: model
Ann source: model
```

**Step 6: Clean up test files (optional)**

```bash
rm data/documents/test_source.json data/documents/test_source.ann.json
```

Or keep them for future testing.

---

## Task 13: Final Integration

**Step 1: Run all backend tests**

```bash
uv run pytest -v
```

Expected: All tests pass

**Step 2: Build frontend production bundle**

```bash
npm run build --prefix /Users/williamthompson/Code/projects/clinical-entity-extraction/projects/textractor/frontend
```

Expected: Build succeeds with no errors

**Step 3: Test production build**

```bash
TEXTRACTOR_DOC_ROOT=./data/documents uv run textractor
```

Visit http://localhost:8000 and verify the UI works correctly with production build.

**Step 4: Create final summary commit (if needed)**

If any final tweaks were made during testing:

```bash
git add -A
git commit -m "test: verify source field feature (Issue #40)

Manual testing confirms:
- AI badges display correctly
- Source transitions work on substantive edits
- Notes don't trigger source changes
- Backward compatibility maintained

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Completion Checklist

- [ ] Backend models have `source` field
- [ ] Backend tests verify backward compatibility
- [ ] Frontend types updated
- [ ] All entity creation includes `source: 'human'`
- [ ] Source transition logic in ReasoningStepList
- [ ] Source transition logic in DocumentAnnotationList
- [ ] AI badges in ReasoningStepList
- [ ] AI badges in DocumentAnnotationList
- [ ] AI badges in AnnotationGraph
- [ ] CSS styling for badges
- [ ] Manual testing completed
- [ ] All tests passing
- [ ] Production build successful

**Next Steps:**
- Create PR referencing Issue #40
- Future: Implement LLM pre-annotation that creates `source: 'model'` entities
