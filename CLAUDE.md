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

# With a terminology file loaded at startup
TEXTRACTOR_DOC_ROOT=./data/documents \
  TEXTRACTOR_TERMINOLOGY_PATH=./data/snomed_subset.tsv \
  uv run textractor
```

FastAPI interactive docs available at `http://localhost:8000/docs` when running.

### Frontend

```bash
cd frontend
npm install        # first time only
npm run dev        # Vite dev server on port 5173 (proxies /api → :8000)
npm run build      # production build → frontend/dist/
```

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
| `terminology.py` | `TerminologyIndex`: loads TSV at startup, in-memory case-insensitive substring search |
| `dependencies.py` | Module-level singletons (`_store`, `_terminology`) initialized in the FastAPI lifespan; exposed via `get_store()` / `get_terminology()` for `Depends()` injection |
| `routers/documents.py` | `GET /api/documents`, `POST /api/documents/upload`, `GET /api/documents/{id}`, `PATCH /api/documents/{id}/metadata`, `DELETE /api/documents/{id}` |
| `routers/annotations.py` | `GET/PUT /api/documents/{id}/annotations` — PUT validates referential integrity (span/step IDs must exist) |
| `routers/terminology.py` | `GET /api/terminology/search?q=`, `GET /api/terminology/info`, `POST /api/terminology/upload` |
| `main.py` | App factory: wires routers, CORS, lifespan, optional `StaticFiles` mount |

### Enhanced Terminology (`src/textractor/terminology/`)

**Note:** This package is under development for more sophisticated SNOMED CT search.

| File | Role |
|---|---|
| `snomed.py` | `SNOMEDSearch`: Uses inverted word index + rapidfuzz for scalable fuzzy search across 800K+ SNOMED descriptions. Pre-filters candidates before fuzzy matching. |

Place SNOMED RF2 release files in `data/terminology/` for use with this module.

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

Terminology TSV (tab-separated, header row required):
```
code	display	system
57054005	Acute myocardial infarction	SNOMED-CT
```

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `TEXTRACTOR_DOC_ROOT` | `./data/documents` | Directory scanned recursively for `*.json` document files |
| `TEXTRACTOR_TERMINOLOGY_PATH` | (none) | TSV file loaded into `TerminologyIndex` at startup |
