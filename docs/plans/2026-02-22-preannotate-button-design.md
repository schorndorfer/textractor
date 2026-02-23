# Pre-Annotate Button Feature Design

**Issue:** [#42](https://github.com/schorndorfer/textractor/issues/42)
**Date:** 2026-02-22
**Status:** Approved

## Overview

Add a "✨ Pre-annotate" button to the annotation panel that calls the pre-annotation endpoint (Issue #41) and loads AI-generated annotations for user review. Results appear as unsaved changes with auto-save blocked until the user makes manual edits, ensuring deliberate review before persistence.

## Requirements

1. ✨ Pre-annotate button in annotation panel header
2. Smart confirmation dialog (only when existing annotations present)
3. Loading indicator during LLM processing (panel notification)
4. Unsaved state management (load as isDirty, block auto-save)
5. Lock-state handling (disable button when document locked)
6. AI attribution via existing source field badges (Issue #40)
7. Error messaging consistent with existing save errors

## Dependencies

**Merged:**
- Issue #40: Source field implementation (PR #46)
- Issue #41: Pre-annotation endpoint (PR #47)

**Existing features:**
- Auto-save with 2-second debounce
- Revert functionality
- Document lock/completed status
- AI badge styling for source='model' annotations

## Architecture

### State Flag Approach

Use a simple `isPreAnnotated` boolean flag to block auto-save after loading AI annotations until the user makes a manual edit.

**State transitions:**

```
User clicks Pre-annotate
  ↓
Confirmation (if existing annotations)
  ↓
API call (loading state)
  ↓
Success: Set annotations, isPreAnnotated=true, isDirty=true
  ↓
Auto-save BLOCKED (isPreAnnotated=true)
  ↓
User makes manual edit
  ↓
Clear isPreAnnotated flag
  ↓
Auto-save RESUMED (normal behavior)
```

### State Management (App.tsx)

**New state:**

```typescript
const [isPreAnnotated, setIsPreAnnotated] = useState(false);
const [preAnnotateLoading, setPreAnnotateLoading] = useState(false);
const [preAnnotateError, setPreAnnotateError] = useState<string | null>(null);
```

**Auto-save modification (line ~116):**

```typescript
useEffect(() => {
  if (!isDirty || !annotations || annotations.completed || isPreAnnotated) return;

  // ... existing auto-save logic
}, [isDirty, annotations, isPreAnnotated]);
```

When `isPreAnnotated` is true, auto-save is blocked.

**Manual edit detection:**

```typescript
const handleAnnotationChange = (updated: AnnotationFile) => {
  // ... existing logic

  setAnnotations(updated);
  setIsDirty(true);

  // Clear pre-annotated flag on manual edit
  if (isPreAnnotated) {
    setIsPreAnnotated(false);
  }
};
```

Any change through this handler (span/step/annotation edits) clears the flag and resumes auto-save.

**Cleanup on document switch:**

```typescript
const loadNewDocument = async () => {
  // ... existing logic

  setIsPreAnnotated(false);
  setPreAnnotateError(null);

  // ... load document
};
```

**Cleanup on revert:**

```typescript
const handleRevert = () => {
  // ... existing logic

  setIsPreAnnotated(false);
  setPreAnnotateError(null);
};
```

## UI Components

### AnnotationPanel Updates

**New props:**

```typescript
interface Props {
  // ... existing props
  onPreAnnotate: () => void;
  isPreAnnotating: boolean;
  preAnnotateError: string | null;
}
```

**Button placement (panel header, line ~98-100):**

```tsx
<div className="panel-header">
  {/* sidebar toggle */}
  {/* title */}

  <button
    onClick={handlePreAnnotate}
    disabled={isLocked || isPreAnnotating}
    className="preannotate-btn"
    title="Generate AI annotations"
  >
    {isPreAnnotating ? '⏳ Pre-annotating...' : '✨ Pre-annotate'}
  </button>

  <button onClick={onRevert} disabled={!isDirty || isLocked}>
    Revert
  </button>

  <label className="completed-checkbox">
    {/* completed checkbox */}
  </label>
</div>
```

**Visual order:** `[✨ Pre-annotate] [Revert] [Completed ☑]`

**Loading indicator (after saveError, line ~102):**

```tsx
{isPreAnnotating && (
  <div className="preannotate-loading">
    ⏳ Generating AI annotations... This may take a moment.
  </div>
)}
```

**Error display (reuse existing saveError location):**

```tsx
{(saveError || preAnnotateError) && !isLocked && (
  <p className="save-error">{saveError || preAnnotateError}</p>
)}
```

**Confirmation dialog:**

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

**Smart confirmation behavior:**
- No annotations → run immediately (no confirmation)
- Has annotations → show confirmation dialog
- User cancels → no action
- User confirms → replace all annotations

### App.tsx Implementation

**API client method (add to api/client.ts):**

```typescript
preannotateDocument: (docId: string) =>
  request<AnnotationFile>(`/documents/${docId}/preannotate`, {
    method: 'POST',
  }),
```

**Handler implementation:**

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

**Pass to AnnotationPanel:**

```tsx
<AnnotationPanel
  // ... existing props
  onPreAnnotate={handlePreAnnotate}
  isPreAnnotating={preAnnotateLoading}
  preAnnotateError={preAnnotateError}
/>
```

## CSS Styling

**Add to frontend/src/index.css:**

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

**Color scheme:**
- Purple (#9333ea) to match AI badge theme from Issue #40
- Consistent visual language for AI-generated content
- Loading indicator uses light purple background for visibility

## Error Handling

**Error sources:**

1. **API key not configured (500)**
   - Message: "API key not configured. Please contact administrator."
   - Indicates ANTHROPIC_API_KEY environment variable missing

2. **LLM service error (502)**
   - Message: "AI service error. Please try again."
   - Covers Claude API failures, timeout, malformed responses

3. **Document locked (403)**
   - Message: "Cannot pre-annotate a locked document."
   - Button is disabled when locked, but backend enforces this too

4. **Network errors**
   - Message: "Pre-annotation failed"
   - Generic fallback for unexpected errors

**Error display:**
- Reuse existing `.save-error` styling and location (line ~102)
- Error persists until:
  - Successful pre-annotation
  - Document switch
  - Revert clicked
  - Document unlocked

**Error clearing:**

```typescript
// On document switch
setPreAnnotateError(null);

// On revert
setPreAnnotateError(null);

// On new pre-annotate attempt
setPreAnnotateError(null);
```

## User Workflow

### Happy Path

1. User opens a document (no existing annotations)
2. User clicks "✨ Pre-annotate"
3. Loading indicator appears: "⏳ Generating AI annotations..."
4. After 5-15 seconds, AI annotations appear with ✨ badges
5. Annotations show as unsaved (isDirty indicator)
6. User reviews annotations, makes edits
7. First edit clears `isPreAnnotated` flag
8. Auto-save kicks in after 2 seconds
9. Annotations saved automatically

### Confirmation Path

1. User opens a document with existing manual annotations
2. User clicks "✨ Pre-annotate"
3. Confirmation dialog: "This will replace all existing annotations..."
4. User clicks "Cancel" → no action
5. User clicks "OK" → proceeds with pre-annotation
6. (continues as happy path)

### Error Path

1. User clicks "✨ Pre-annotate"
2. API call fails (e.g., 502 error)
3. Error message appears: "AI service error. Please try again."
4. User can:
   - Try again (clicks button again)
   - Continue with manual annotation
   - Switch documents (error clears)

### Review and Discard Path

1. User clicks "✨ Pre-annotate"
2. AI annotations load as unsaved changes
3. User reviews and decides they don't want them
4. User clicks "Revert"
5. Annotations revert to original state
6. `isPreAnnotated` flag cleared
7. User continues with manual annotation

## Edge Cases

### Document Locking

- Button disabled when `annotations.completed === true`
- Backend enforces 403 response if somehow called on locked document
- Lock icon visible in panel header

### Document Switching

- If user switches documents while pre-annotating:
  - Request may still complete
  - But state has been reset for new document
  - No effect on new document (request ignored)

### Multiple Clicks

- Button disabled during loading (`isPreAnnotating === true`)
- User cannot trigger multiple concurrent requests

### Auto-Save Race Conditions

- `isPreAnnotated` flag prevents auto-save after loading
- User must make manual edit to resume auto-save
- No race between "load AI annotations" and "auto-save them"

### Empty Pre-Annotation Results

- If LLM returns empty annotations (no spans/steps/annotations):
  - Still loads as-is (replaces existing with empty)
  - User can see that AI found nothing
  - Can revert or manually annotate

### Partial Pre-Annotation Results

- If span validation fails for some spans:
  - Backend returns partial results (valid spans only)
  - User sees whatever the LLM successfully generated
  - AI badges appear on all returned items (source='model')

## Testing Strategy

### Manual Testing

1. **Basic flow:**
   - Empty document → Pre-annotate → Review → Edit → Auto-save

2. **Confirmation:**
   - Document with annotations → Pre-annotate → Confirm → Replace

3. **Revert:**
   - Pre-annotate → Review → Revert → Back to original

4. **Locked document:**
   - Mark completed → Button disabled → Cannot pre-annotate

5. **Error handling:**
   - No API key → Error message
   - Network error → Error message

6. **Auto-save blocking:**
   - Pre-annotate → Wait 10 seconds → Still not saved
   - Make edit → Wait 2 seconds → Auto-saved

### Integration Testing

1. **State flag lifecycle:**
   - Verify `isPreAnnotated` set on load
   - Verify cleared on manual edit
   - Verify cleared on revert
   - Verify cleared on document switch

2. **Error clearing:**
   - Error shown → Switch documents → Error cleared
   - Error shown → Successful pre-annotate → Error cleared

3. **AI badges:**
   - Pre-annotated content has ✨ badges
   - Manually edited items lose badges (source flips to 'human')

## Implementation Details

### Files to Modify

**Frontend:**
- `frontend/src/App.tsx` - Add state, handler, auto-save modification
- `frontend/src/components/AnnotationPanel.tsx` - Add button, props, confirmation
- `frontend/src/api/client.ts` - Add preannotateDocument method
- `frontend/src/index.css` - Add styling for button and loading indicator

### Files to Create

None - all changes are modifications to existing files.

### Props Threading

```
App.tsx
  ↓ onPreAnnotate={handlePreAnnotate}
  ↓ isPreAnnotating={preAnnotateLoading}
  ↓ preAnnotateError={preAnnotateError}
AnnotationPanel.tsx
```

Simple prop drilling - only one level deep.

## Future Enhancements

- **Progress updates:** WebSocket or polling for "Extracting terms...", "Generating annotations..."
- **Partial merge:** Option to merge AI annotations with existing instead of replace
- **AI annotation review mode:** Dedicated UI for accepting/rejecting individual AI suggestions
- **Confidence scores:** Display LLM confidence for each annotation
- **Batch pre-annotation:** Pre-annotate multiple documents at once
- **Settings:** Configure LLM model, fuzzy threshold from UI

## Success Criteria

1. Button appears in annotation panel header
2. Button disabled when document is locked
3. Confirmation dialog shows when replacing existing annotations
4. Loading indicator visible during API call
5. AI annotations load as unsaved changes (isDirty: true)
6. Auto-save blocked until user makes manual edit
7. Errors display in consistent location with user-friendly messages
8. AI badges (✨) appear on model-generated annotations
9. Revert button clears pre-annotated content
10. Manual edits trigger source field flip to 'human' (existing behavior)
