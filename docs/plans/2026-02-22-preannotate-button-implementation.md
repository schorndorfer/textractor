# Pre-Annotate Button Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a ✨ Pre-annotate button to the annotation panel that generates AI annotations with smart confirmation and auto-save blocking until manual review.

**Architecture:** State flag approach using `isPreAnnotated` to block auto-save after loading AI-generated annotations until user makes manual edits. Button integrated into AnnotationPanel header with loading indicator and error display.

**Tech Stack:** React, TypeScript, FastAPI, existing auto-save infrastructure

---

## Task 1: Add API Client Method

**Files:**
- Modify: `frontend/src/api/client.ts`

**Step 1: Add preannotateDocument method**

Add to the `api` object in `frontend/src/api/client.ts` (after the `saveAnnotations` method, around line 51):

```typescript
preannotateDocument: (docId: string) =>
  request<AnnotationFile>(`/documents/${docId}/preannotate`, {
    method: 'POST',
  }),
```

**Step 2: Verify TypeScript compilation**

```bash
npx --prefix /Users/williamthompson/Code/projects/clinical-entity-extraction/projects/textractor/frontend tsc --noEmit
```

Expected: PASS (no errors)

**Step 3: Test import**

```bash
npx --prefix /Users/williamthompson/Code/projects/clinical-entity-extraction/projects/textractor/frontend tsc --noEmit 2>&1 | grep -E "(error|warning)" || echo "✓ TypeScript check passed"
```

Expected: "✓ TypeScript check passed"

**Step 4: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat: add preannotateDocument API client method (Issue #42)

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: Add State Management in App.tsx

**Files:**
- Modify: `frontend/src/App.tsx`

**Step 1: Add state declarations**

After the existing state declarations (around line 27, after `activeTab` state):

```typescript
// Pre-annotation state
const [isPreAnnotated, setIsPreAnnotated] = useState(false);
const [preAnnotateLoading, setPreAnnotateLoading] = useState(false);
const [preAnnotateError, setPreAnnotateError] = useState<string | null>(null);
```

**Step 2: Verify TypeScript compilation**

```bash
npx --prefix /Users/williamthompson/Code/projects/clinical-entity-extraction/projects/textractor/frontend tsc --noEmit
```

Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: add pre-annotation state management (Issue #42)

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: Modify Auto-Save Logic

**Files:**
- Modify: `frontend/src/App.tsx`

**Step 1: Update auto-save useEffect**

Find the auto-save useEffect (around line 115). Update the first line of the effect:

```typescript
// Debounced auto-save when annotations change
useEffect(() => {
  if (!isDirty || !annotations || annotations.completed || isPreAnnotated) return; // Don't auto-save locked documents or pre-annotated content

  // Clear existing timeout
  if (autoSaveTimeoutRef.current) {
    clearTimeout(autoSaveTimeoutRef.current);
  }

  // Set new timeout for auto-save
  autoSaveTimeoutRef.current = setTimeout(() => {
    saveAnnotations();
  }, AUTO_SAVE.DEBOUNCE_MS);

  return () => {
    if (autoSaveTimeoutRef.current) {
      clearTimeout(autoSaveTimeoutRef.current);
    }
  };
}, [isDirty, annotations, isPreAnnotated]); // Add isPreAnnotated to dependency array
```

**Step 2: Verify TypeScript compilation**

```bash
npx --prefix /Users/williamthompson/Code/projects/clinical-entity-extraction/projects/textractor/frontend tsc --noEmit
```

Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: block auto-save for pre-annotated content (Issue #42)

Auto-save skipped when isPreAnnotated flag is true, ensuring user
review before persistence.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: Add Manual Edit Detection

**Files:**
- Modify: `frontend/src/App.tsx`

**Step 1: Update handleAnnotationChange**

Find the `handleAnnotationChange` function (around line 98). Update it to clear the `isPreAnnotated` flag:

```typescript
const handleAnnotationChange = (updated: AnnotationFile) => {
  // Don't allow changes to locked documents (except toggling completed status)
  if (annotations?.completed && updated.completed) {
    return;
  }
  setAnnotations(updated);
  setIsDirty(true);

  // Clear pre-annotated flag on manual edit
  // This allows auto-save to resume
  if (isPreAnnotated) {
    setIsPreAnnotated(false);
  }
};
```

**Step 2: Verify TypeScript compilation**

```bash
npx --prefix /Users/williamthompson/Code/projects/clinical-entity-extraction/projects/textractor/frontend tsc --noEmit
```

Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: clear pre-annotated flag on manual edit (Issue #42)

When user makes any edit after pre-annotation, clear the flag to
resume auto-save behavior.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5: Update Cleanup Functions

**Files:**
- Modify: `frontend/src/App.tsx`

**Step 1: Update handleRevert function**

Find the `handleRevert` function (around line 182). Add cleanup for pre-annotation state:

```typescript
const handleRevert = () => {
  if (originalAnnotations) {
    setAnnotations(deepClone(originalAnnotations));
    setIsDirty(false);
    setSaveError(null);
    setPreAnnotateError(null); // Clear pre-annotate errors
    setIsPreAnnotated(false); // Clear pre-annotated flag
  }
};
```

**Step 2: Update loadNewDocument function**

Find the `loadNewDocument` function inside the document switching useEffect (around line 63). Add cleanup:

```typescript
const loadNewDocument = async () => {
  if (isDirty && annotations && !isSavingRef.current) {
    await saveAnnotations();
  }

  setLoading(true);
  setSelectedAnnotationId(null); // Clear selection when switching documents
  setFocusedSpanId(null); // Clear focused span when switching documents
  setIsPreAnnotated(false); // Clear pre-annotated flag
  setPreAnnotateError(null); // Clear pre-annotate errors

  try {
    const [doc, ann] = await Promise.all([
      api.getDocument(selectedDocId),
      api.getAnnotations(selectedDocId)
    ]);
    setCurrentDoc(doc);
    setAnnotations(ann);
    setOriginalAnnotations(deepClone(ann));
    setIsDirty(false);
    setSaveError(null);
  } catch (error) {
    console.error(error);
  } finally {
    setLoading(false);
  }
};
```

**Step 3: Verify TypeScript compilation**

```bash
npx --prefix /Users/williamthompson/Code/projects/clinical-entity-extraction/projects/textractor/frontend tsc --noEmit
```

Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: cleanup pre-annotation state on revert and document switch (Issue #42)

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 6: Add Pre-Annotate Handler

**Files:**
- Modify: `frontend/src/App.tsx`

**Step 1: Add handlePreAnnotate function**

Add after the `handleRevert` function (around line 188):

```typescript
const handlePreAnnotate = async () => {
  if (!selectedDocId) return;

  setPreAnnotateLoading(true);
  setPreAnnotateError(null);

  try {
    const aiAnnotations = await api.preannotateDocument(selectedDocId);

    // Load AI annotations as unsaved changes
    setAnnotations(aiAnnotations);
    setIsPreAnnotated(true);
    setIsDirty(true);

  } catch (err) {
    const errorStr = String(err);
    let errorMsg = 'Pre-annotation failed';

    if (errorStr.includes('500') && errorStr.includes('ANTHROPIC_API_KEY')) {
      errorMsg = 'API key not configured. Please contact administrator.';
    } else if (errorStr.includes('502')) {
      errorMsg = 'AI service error. Please try again.';
    } else if (errorStr.includes('403')) {
      errorMsg = 'Cannot pre-annotate a locked document.';
    }

    setPreAnnotateError(errorMsg);
  } finally {
    setPreAnnotateLoading(false);
  }
};
```

**Step 2: Verify TypeScript compilation**

```bash
npx --prefix /Users/williamthompson/Code/projects/clinical-entity-extraction/projects/textractor/frontend tsc --noEmit
```

Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: add handlePreAnnotate with error handling (Issue #42)

Calls pre-annotation endpoint, loads results as unsaved changes,
handles errors with user-friendly messages.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 7: Pass Props to AnnotationPanel

**Files:**
- Modify: `frontend/src/App.tsx`

**Step 1: Add props to AnnotationPanel component**

Find where `AnnotationPanel` is rendered (around line 230+). Add the new props:

```tsx
<AnnotationPanel
  annotations={annotations}
  onChange={handleAnnotationChange}
  onRevert={handleRevert}
  isDirty={isDirty}
  saveError={saveError}
  spanColorMap={spanColorMap}
  docAnnColorMap={docAnnColorMap}
  stepColorMap={stepColorMap}
  selectedAnnotationId={selectedAnnotationId}
  onAnnotationSelect={handleAnnotationSelect}
  onToggleCollapse={toggleRightSidebar}
  collapsed={rightSidebarCollapsed}
  onSpanClick={handleSpanClick}
  onPreAnnotate={handlePreAnnotate}
  isPreAnnotating={preAnnotateLoading}
  preAnnotateError={preAnnotateError}
/>
```

**Step 2: Verify TypeScript compilation**

```bash
npx --prefix /Users/williamthompson/Code/projects/clinical-entity-extraction/projects/textractor/frontend tsc --noEmit
```

Expected: Will fail - AnnotationPanel doesn't have these props yet

**Step 3: Note the error**

This is expected - we'll fix it in the next task by updating AnnotationPanel.

---

## Task 8: Update AnnotationPanel Component

**Files:**
- Modify: `frontend/src/components/AnnotationPanel.tsx`

**Step 1: Update Props interface**

At the top of the file (around line 7-21), add the new props:

```typescript
interface Props {
  annotations: AnnotationFile;
  onChange: (ann: AnnotationFile) => void;
  onRevert: () => void;
  isDirty: boolean;
  saveError: string | null;
  spanColorMap: SpanColorMap;
  docAnnColorMap: SpanColorMap;
  stepColorMap: SpanColorMap;
  selectedAnnotationId: string | null;
  onAnnotationSelect: (annotationId: string | null) => void;
  onToggleCollapse?: () => void;
  collapsed?: boolean;
  onSpanClick?: (spanId: string) => void;
  onPreAnnotate: () => void;
  isPreAnnotating: boolean;
  preAnnotateError: string | null;
}
```

**Step 2: Destructure new props**

Update the function signature (around line 23):

```typescript
export function AnnotationPanel({
  annotations,
  onChange,
  onRevert,
  isDirty,
  saveError,
  spanColorMap,
  docAnnColorMap,
  stepColorMap,
  selectedAnnotationId,
  onAnnotationSelect,
  onToggleCollapse,
  collapsed,
  onSpanClick,
  onPreAnnotate,
  isPreAnnotating,
  preAnnotateError,
}: Props) {
```

**Step 3: Add confirmation handler**

Add after the `toggleCompleted` function (around line 73):

```typescript
const handlePreAnnotate = () => {
  const hasExistingAnnotations =
    annotations.spans.length > 0 ||
    annotations.reasoning_steps.length > 0 ||
    annotations.document_annotations.length > 0;

  if (hasExistingAnnotations) {
    const confirmed = window.confirm(
      'This will replace all existing annotations with AI-generated content. Continue?'
    );
    if (!confirmed) return;
  }

  onPreAnnotate();
};
```

**Step 4: Update panel header JSX**

Find the panel header section (around line 75). Update to include the Pre-annotate button:

```tsx
<div className="panel-header">
  {onToggleCollapse && (
    <button
      className="sidebar-toggle"
      onClick={onToggleCollapse}
      title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
    >
      ›
    </button>
  )}
  <h2>
    Annotations {isLocked && <span className="lock-icon" title="Document is locked">🔒</span>}
  </h2>
  <button
    onClick={handlePreAnnotate}
    disabled={isLocked || isPreAnnotating}
    className="preannotate-btn"
    title="Generate AI annotations"
  >
    {isPreAnnotating ? '⏳ Pre-annotating...' : '✨ Pre-annotate'}
  </button>
  <button onClick={onRevert} disabled={!isDirty || isLocked} className={`save-btn${isDirty ? ' dirty' : ''}`}>
    Revert
  </button>
  <label className="completed-checkbox">
    <input
      type="checkbox"
      checked={annotations.completed || false}
      onChange={toggleCompleted}
    />
    <span>Completed</span>
  </label>
</div>
```

**Step 5: Add loading indicator**

After the panel header (around line 101, before the `{saveError && ...}` line), add:

```tsx
{isPreAnnotating && (
  <div className="preannotate-loading">
    ⏳ Generating AI annotations... This may take a moment.
  </div>
)}
```

**Step 6: Update error display**

Find the saveError display (around line 102). Update to show both errors:

```tsx
{(saveError || preAnnotateError) && !isLocked && (
  <p className="save-error">{saveError || preAnnotateError}</p>
)}
```

**Step 7: Verify TypeScript compilation**

```bash
npx --prefix /Users/williamthompson/Code/projects/clinical-entity-extraction/projects/textractor/frontend tsc --noEmit
```

Expected: PASS

**Step 8: Commit**

```bash
git add frontend/src/components/AnnotationPanel.tsx frontend/src/App.tsx
git commit -m "feat: add Pre-annotate button to AnnotationPanel (Issue #42)

Includes smart confirmation, loading indicator, and error display.
Button disabled when document is locked or already pre-annotating.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 9: Add CSS Styling

**Files:**
- Modify: `frontend/src/index.css`

**Step 1: Add pre-annotate button styles**

Add to the end of `frontend/src/index.css`:

```css
/* Pre-annotate button */
.preannotate-btn {
  padding: 6px 12px;
  border: 1px solid #9333ea;
  background: #9333ea;
  color: white;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  margin-right: 8px;
  transition: background 0.2s;
}

.preannotate-btn:hover:not(:disabled) {
  background: #7e22ce;
}

.preannotate-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Loading indicator in panel */
.preannotate-loading {
  padding: 12px;
  background: #ede9fe;
  border-left: 4px solid #9333ea;
  color: #6b21a8;
  font-size: 14px;
  margin-bottom: 12px;
}
```

**Step 2: Build frontend to verify styles**

```bash
npm run build --prefix /Users/williamthompson/Code/projects/clinical-entity-extraction/projects/textractor/frontend
```

Expected: Build succeeds

**Step 3: Commit**

```bash
git add frontend/src/index.css
git commit -m "style: add CSS for pre-annotate button and loading indicator (Issue #42)

Purple theme matching AI badge styling from Issue #40.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 10: Manual Testing - Basic Flow

**Files:**
- Test: End-to-end user workflow

**Step 1: Start backend with API key**

```bash
export ANTHROPIC_API_KEY="your-api-key-here"
TEXTRACTOR_DOC_ROOT=./data/documents uv run textractor
```

Expected: Backend starts on port 8000

**Step 2: Start frontend dev server**

In another terminal:

```bash
cd frontend && npm run dev
```

Expected: Frontend starts on port 5173

**Step 3: Test basic pre-annotation flow**

1. Open http://localhost:5173
2. Select a document (preferably one without existing annotations)
3. Click "✨ Pre-annotate" button
4. Verify:
   - Loading indicator appears: "⏳ Generating AI annotations..."
   - Button shows "⏳ Pre-annotating..." and is disabled
   - After 5-15 seconds, annotations appear
   - All annotations have ✨ badges (source='model')
   - Document shows as dirty/unsaved
5. Wait 10 seconds
6. Verify: Annotations are NOT auto-saved (still dirty)
7. Make a manual edit (e.g., delete a span or add a note)
8. Wait 3 seconds
9. Verify: Annotations auto-save (dirty indicator clears)

**Step 4: Test confirmation dialog**

1. Select a different document
2. Manually create some annotations (spans, steps, or document annotations)
3. Click "✨ Pre-annotate"
4. Verify: Confirmation dialog appears with message about replacing
5. Click "Cancel"
6. Verify: No action taken, manual annotations still present
7. Click "✨ Pre-annotate" again
8. Click "OK" in confirmation
9. Verify: Manual annotations replaced with AI annotations

**Step 5: Test revert**

1. Pre-annotate a document
2. Review the AI annotations
3. Click "Revert" button
4. Verify:
   - Annotations cleared (back to original state)
   - Dirty indicator cleared
   - `isPreAnnotated` flag cleared (can verify by making edit → auto-saves normally)

**Step 6: Test locked document**

1. Pre-annotate a document
2. Make an edit (to trigger auto-save)
3. Check the "Completed" checkbox
4. Verify: "✨ Pre-annotate" button is disabled
5. Uncheck "Completed"
6. Verify: Button is enabled again

**Step 7: Test error handling (no API key)**

Stop the backend, then restart without API key:

```bash
unset ANTHROPIC_API_KEY
TEXTRACTOR_DOC_ROOT=./data/documents uv run textractor
```

1. Click "✨ Pre-annotate"
2. Verify: Error message appears: "API key not configured. Please contact administrator."
3. Error persists until you switch documents or click Pre-annotate again

---

## Task 11: Manual Testing - Edge Cases

**Files:**
- Test: Edge cases and error scenarios

**Step 1: Test document switching during pre-annotation**

1. Start pre-annotation on document A
2. While loading indicator is visible, switch to document B
3. Verify:
   - Loading indicator disappears
   - Document B loads normally
   - No annotations from document A leak into document B

**Step 2: Test empty pre-annotation result**

Create a test document with non-medical text:

```bash
cat > data/documents/test_empty.json <<'EOF'
{
  "id": "test_empty",
  "text": "This is just some random text with no medical content whatsoever. Just filler text.",
  "metadata": {}
}
EOF
```

1. Select the test_empty document
2. Click "✨ Pre-annotate"
3. Verify:
   - Loading completes
   - Document may have empty or minimal annotations
   - No errors shown
   - Can still manually annotate

**Step 3: Test multiple clicks**

1. Click "✨ Pre-annotate"
2. While loading, try clicking the button again
3. Verify: Button is disabled, can't trigger multiple requests

**Step 4: Test auto-save blocking persistence**

1. Pre-annotate a document
2. Wait 30 seconds without making any edits
3. Verify: Document still shows as dirty (not auto-saved)
4. Switch to another document
5. Come back to the pre-annotated document
6. Verify: Annotations are still unsaved (reverted to original)

**Step 5: Cleanup test files**

```bash
rm data/documents/test_empty.json
```

---

## Task 12: Final Integration and Documentation

**Files:**
- Test: Full system integration

**Step 1: Run frontend build**

```bash
npm run build --prefix /Users/williamthompson/Code/projects/clinical-entity-extraction/projects/textractor/frontend
```

Expected: Build succeeds with no errors

**Step 2: Test production build**

```bash
ANTHROPIC_API_KEY="your-key" TEXTRACTOR_DOC_ROOT=./data/documents uv run textractor
```

Visit http://localhost:8000 and verify:
- Pre-annotate button appears and works
- Loading indicator displays correctly
- Errors display correctly
- AI badges appear on generated annotations

**Step 3: Verify all commits are present**

```bash
git log --oneline --grep="Issue #42"
```

Expected: See all commits for this feature

**Step 4: Create summary of changes**

Create a summary for the PR:

```
Added ✨ Pre-annotate button to annotation panel (Issue #42):

- Smart confirmation dialog (only when replacing existing annotations)
- Loading indicator during LLM processing
- Auto-save blocked until user makes manual edit
- Error handling for API key, locked documents, and service errors
- Purple button styling matching AI badge theme
- Props threading: App.tsx → AnnotationPanel
- State management with isPreAnnotated flag

Testing:
- Manual testing completed for all user workflows
- Confirmation dialog behavior verified
- Auto-save blocking verified
- Error scenarios tested
- Edge cases covered (document switching, multiple clicks, empty results)
```

---

## Completion Checklist

- [ ] API client method added
- [ ] State management in App.tsx
- [ ] Auto-save blocking logic
- [ ] Manual edit detection
- [ ] Cleanup functions updated
- [ ] Pre-annotate handler implemented
- [ ] AnnotationPanel props updated
- [ ] Button and confirmation logic added
- [ ] Loading indicator added
- [ ] Error display integrated
- [ ] CSS styling added
- [ ] Basic flow manual testing
- [ ] Edge cases manual testing
- [ ] Production build successful
- [ ] All commits present

**Next Steps:**
- Create branch for this work
- Open PR referencing Issue #42
- Request review
- Merge after approval
