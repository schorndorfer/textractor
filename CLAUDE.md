# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Textractor is a clinical text annotation tool with a FastAPI backend and React/TypeScript frontend. It annotates documents with SNOMED-style concepts at the document level, linked to text span evidence and structured intermediate reasoning steps.

## Common Commands

### Backend

```bash
uv sync                                                     # install/update dependencies

# Run backend (port 8000, hot-reload)
TEXTRACTOR_DOC_ROOT=./data/documents uv run textractor
```

FastAPI interactive docs available at `http://localhost:8000/docs` when running.

### Frontend

```bash
cd frontend
npm install        # first time only
npm run dev        # Vite dev server on port 5173 (proxies /api → :8000)
npm run build      # production build → frontend/dist/
```

### Testing

```bash
uv sync --extra dev                    # install test dependencies (pytest)
uv run pytest                          # run all tests
uv run pytest tests/test_snomed.py     # run specific test file
uv run pytest -v                       # verbose output
uv run pytest -k "search"              # run tests matching pattern
```

**Note:** SNOMED tests require SNOMED CT RF2 files in `data/terminology/SnomedCT/`. Tests will skip if data is not present.

### Dev mode (both together)

```
Terminal 1: TEXTRACTOR_DOC_ROOT=./data/documents uv run textractor
Terminal 2: cd frontend && npm run dev
Browser:    http://localhost:5173
```

### Production

`npm run build` in `frontend/`, then `uv run textractor` — FastAPI auto-serves `frontend/dist/` via `StaticFiles`.

## Architecture

### Backend (`src/textractor/api/`)

| File | Role |
|---|---|
| `models.py` | All Pydantic models: `Span`, `ReasoningStep` (with optional `note` field), `DocumentAnnotation`, `AnnotationFile`, `Document`, `DocumentSummary`, `TerminologyConcept`, `TerminologyInfo` |
| `storage.py` | `DocumentStore`: recursively scans `TEXTRACTOR_DOC_ROOT` for `*.json` docs; companion annotations stored flat as `{doc_id}.ann.json` in root |
| `enhanced_terminology.py` | `EnhancedTerminologyIndex`: SNOMED CT terminology search using SQLite FTS5. Converts SNOMED results to `TerminologyConcept` format. |
| `dependencies.py` | Module-level singletons (`_store`, `_terminology`) initialized in the FastAPI lifespan. Loads SNOMED from `data/terminology/SnomedCT/` if available. |
| `routers/documents.py` | `GET /api/documents`, `POST /api/documents/upload`, `GET /api/documents/{id}`, `PATCH /api/documents/{id}/metadata`, `DELETE /api/documents/{id}` |
| `routers/annotations.py` | `GET/PUT /api/documents/{id}/annotations` — PUT validates referential integrity (span/step IDs must exist) |
| `routers/preannotate.py` | `POST /api/documents/{id}/preannotate` — generates AI annotations using Claude, validates spans via rapidfuzz, returns AnnotationFile without auto-save |
| `routers/terminology.py` | `GET /api/terminology/search?q=`, `GET /api/terminology/info`. Provides SNOMED CT full-text search. |
| `llm.py` | Two-stage LLM pipeline: `extract_medical_terms` (Stage 1), `generate_annotations_raw` (Stage 2), `validate_and_convert_annotations` (span recovery + AnnotationFile conversion) |
| `main.py` | App factory: wires routers, CORS, lifespan, optional `StaticFiles` mount. Initializes SNOMED terminology on startup. |

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

Filtering happens post-generation with cascade deletion of orphaned reasoning steps and spans. Check backend logs for filtering statistics.

### Hierarchy Enforcement

Pre-annotation enforces strict hierarchical progression:

**Strict hierarchy flow:**
- Spans (text evidence) → Reasoning Steps (intermediate concepts) → Document Annotations (final findings)
- Every reasoning step must reference ≥1 span
- Every document annotation must reference ≥1 reasoning step
- No direct span links from document annotations (`evidence_span_ids` is empty for AI)

**Validation:**
- LLM tool schema prevents direct span links (`evidence_span_indices` removed from schema)
- Schema enforces `minItems: 1` on `span_indices` and `reasoning_step_indices`
- Post-processing filters violations in `validate_and_convert_annotations()`
- Reasoning steps with 0 spans are filtered
- Document annotations with 0 reasoning steps are filtered
- Detailed logging shows what was filtered ("Hierarchy validation: filtered ...")

**Human flexibility:**
- Hierarchy rules only apply to AI-generated annotations (`source='model'`)
- Human annotations retain full flexibility including direct span links
- Existing annotations with direct links continue to work

Check backend logs for "Hierarchy validation:" output to see filtering statistics.

### Clear All Button

The annotation panel includes a **🗑️ Clear All** button for deleting all annotations.

**Location**: Between the Pre-annotate and Revert buttons in the annotation panel header

**Behavior**:
- Deletes all spans, reasoning steps, and document annotations
- Shows confirmation dialog: "This will delete all annotations... This cannot be undone. Continue?"
- Disabled when document is locked (`completed === true`)
- Disabled when no annotations exist (all three arrays empty)
- Triggers normal auto-save workflow after clearing (2-second debounce)
- User can still revert within 2 seconds before auto-save persists

**Implementation**: `frontend/src/components/AnnotationPanel.tsx:handleClear()`

**Styling**: Red/danger color scheme (transparent background with red border, red background on hover)

### SNOMED CT Terminology (`src/textractor/terminology/`)

**SNOMED CT integration** - place SNOMED RF2 files in `data/terminology/SnomedCT/` and they will be automatically loaded at startup.

| File | Role |
|---|---|
| `snomed.py` | `SNOMEDSearch`: Uses SQLite FTS5 with trigram tokenization for persistent, memory-efficient full-text search. Database stored at `data/terminology/snomed.db`. Automatically built from RF2 files on first load. |

**Features:**
- **Persistent storage**: Database built once, instant startup on subsequent runs
- **Low memory footprint**: ~50MB RAM for 2.6M+ SNOMED descriptions
- **Fast full-text search**: FTS5 trigram tokenization enables substring matching
- **Custom ranking**: Multi-factor scoring (exact match, prefix, word boundary, position)
- **Deduplication**: Returns one result per concept ID (highest scoring)

### Frontend (`frontend/src/`)

State lives entirely in `App.tsx` (`selectedDocId`, `annotations`, `isDirty`, `selectedAnnotationId`, `activeTab`). No external state library.

**Key UI behavior:**
- Selecting a document annotation auto-switches to "Annotation Graph" tab
- Deselecting an annotation auto-switches back to "Document Text" tab
- Annotation selection filters visible spans to only those linked to the selected annotation

| Component | Role |
|---|---|
| `DocumentViewer` | Renders text; `mouseUp` handler calls `getCharOffset()` (DOM tree walk) to compute character offsets into `doc.text`, then emits a new `Span`. Works correctly through `<mark>` elements. |
| `SpanHighlighter` | Renders text + `<mark>` highlights. Handles overlapping spans via an event-based depth counter (open/close events sorted by position). |
| `ConceptSearch` | Debounced (250ms) autocomplete calling `/api/terminology/search`. Uses `onMouseDown` on dropdown items (fires before `onBlur` on input) so selection isn't lost. |
| `AnnotationPanel` | Owns cascading-delete logic: span deletion cleans `span_ids` in all steps and `evidence_span_ids` in all document annotations; step deletion cleans `reasoning_step_ids` in all document annotations. |
| `ReasoningStepList` | Intermediate concept annotations with optional free-form notes, each linked to 0+ spans via checkboxes. |
| `DocumentAnnotationList` | Final document-level annotations linked to 0+ spans and 0+ reasoning steps. Clicking selects/highlights the annotation. |
| `DocumentList` | Project-based organization with collapsible groups. Projects stored in `doc.metadata.project`. Uses "Add Files" dialog to move documents between projects. |
| `AnnotationGraph` | React Flow interactive graph showing document annotation → reasoning steps → spans. Nodes are draggable, zoomable, pannable. |

### Data model

Input document (`{doc_id}.json`):
```json
{ "id": "doc_001", "text": "...", "metadata": {} }
```

Annotation output (`{doc_id}.ann.json`):
```json
{
  "doc_id": "doc_001",
  "spans": [{ "id": "span_xxx", "start": 0, "end": 10, "text": "chest pain" }],
  "reasoning_steps": [{
    "id": "step_xxx",
    "concept": { "code": "...", "display": "...", "system": "SNOMED-CT" },
    "span_ids": ["span_xxx"],
    "note": "Optional free-form reasoning notes"
  }],
  "document_annotations": [{
    "id": "ann_xxx",
    "concept": { ... },
    "evidence_span_ids": ["span_xxx"],
    "reasoning_step_ids": ["step_xxx"]
  }]
}
```

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `TEXTRACTOR_DOC_ROOT` | `./data/documents` | Directory scanned recursively for `*.json` document files |
| `ANTHROPIC_API_KEY` | (required for pre-annotation) | Anthropic API key for Claude AI access |
| `TEXTRACTOR_LLM_MODEL` | `claude-sonnet-4-5` | Model name for annotation generation |
| `TEXTRACTOR_FUZZY_THRESHOLD` | `90` | Minimum similarity (0-100) for span offset recovery |

**SNOMED CT Setup:**
- Place SNOMED CT RF2 files in `data/terminology/SnomedCT/`
- SQLite database will be automatically built at `data/terminology/snomed.db` on first startup
- Subsequent startups will reuse the existing database

- When resolving github issues, always create a branch, then a PR