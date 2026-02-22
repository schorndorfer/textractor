# Source Field for Annotation Provenance

**Issue:** [#40](https://github.com/schorndorfer/textractor/issues/40)
**Date:** 2026-02-22
**Status:** Approved

## Overview

Add a `source` field to annotation models (`Span`, `ReasoningStep`, `DocumentAnnotation`) to distinguish between human-created and model-generated annotations. This serves as foundational infrastructure for future LLM pre-annotation capabilities.

## Requirements

1. Add `source: Literal['human', 'model']` field with default `'human'` to three models
2. Backward-compatible with existing `.ann.json` files (no migration needed)
3. Frontend visual differentiation for model-generated annotations
4. Automatic source transition from `'model'` → `'human'` when users make substantive edits

## Data Model Changes

### Backend (src/textractor/api/models.py)

Add `source` field to:
- `Span`: `source: Literal['human', 'model'] = 'human'`
- `ReasoningStep`: `source: Literal['human', 'model'] = 'human'`
- `DocumentAnnotation`: `source: Literal['human', 'model'] = 'human'`

Pydantic's default value ensures backward compatibility.

### Frontend (frontend/src/types/index.ts)

Add `source: 'human' | 'model'` to matching TypeScript interfaces.

## Source Transition Logic

### What triggers 'model' → 'human' transition?

**ReasoningStep:**
- ✅ Changing the `concept` field
- ✅ Adding/removing linked `span_ids` (checkbox toggles)
- ❌ Editing the `note` field (notes are commentary only)

**DocumentAnnotation:**
- ✅ Changing the `concept` field
- ✅ Adding/removing `evidence_span_ids`
- ✅ Adding/removing `reasoning_step_ids`
- ❌ Editing the `note` field

**Span:**
- No editable fields (immutable once created)
- User-created spans always start as `'human'`
- Future model-generated spans would start as `'model'`

### Transition rules

- `'model'` → `'human'`: Allowed (user edits model output)
- `'human'` → `'model'`: Never happens
- One-way transition only

## Visual Differentiation

### Badge placement

- ✅ `ReasoningStepList`: Show badge for `source: 'model'`
- ✅ `DocumentAnnotationList`: Show badge for `source: 'model'`
- ❌ `SpanList`: No badge (spans are just text selections)
- ✅ `AnnotationGraph`: Show badge on nodes for model-generated items

### Badge design

- Icon-based: ✨ (sparkles emoji)
- Purple circular background (`#9333ea`)
- Inline with concept display
- Tooltip: "Model-generated"
- Example: `[✨] Hypertensive disorder`

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
}
```

### Badge behavior

- Badge visible when `source === 'model'`
- Badge disappears after edit (source flips to `'human'`)
- Provides clear visual feedback

## Implementation Approach

**Frontend-Driven Source Tracking** (Approach 1)

- Backend stores the `source` field, no validation logic
- Frontend components detect substantive edits and update source
- Source transition logic lives in React components where user actions occur
- Simple, clear separation of concerns

## Implementation Tasks

### Backend
1. Update `models.py` - add `source` field to Span, ReasoningStep, DocumentAnnotation
2. No API changes needed (field flows through existing endpoints)
3. No migration needed (Pydantic defaults handle it)

### Frontend
1. Update `types/index.ts` - add `source` to interfaces
2. Update entity creation - set `source: 'human'` for new entities:
   - `DocumentViewer.tsx` (spans)
   - `ReasoningStepList.tsx` (steps)
   - `DocumentAnnotationList.tsx` (annotations)
3. Add source transition logic:
   - `ReasoningStepList.tsx`: Detect concept/span_ids changes
   - `DocumentAnnotationList.tsx`: Detect concept/evidence/step changes
4. Add visual badges:
   - `ReasoningStepList.tsx`: Render badge when `source === 'model'`
   - `DocumentAnnotationList.tsx`: Render badge when `source === 'model'`
   - `AnnotationGraph.tsx`: Render badge on graph nodes
5. Add CSS styling for `.ai-badge`

## Testing

- Manually verify backward compatibility with existing `.ann.json` files
- Create mock model-generated annotations to test badge rendering
- Test source transitions by editing concepts and linked IDs
- Verify notes don't trigger source changes
- Test badge appearance/disappearance on edit

## Future Work

This design lays the groundwork for:
- LLM pre-annotation features
- Tracking annotation quality metrics by source
- Filtering/searching annotations by source
- Analytics on human vs. model annotation patterns
