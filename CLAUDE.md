# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Textractor is a clinical text annotation tool with a FastAPI backend and React/TypeScript frontend. It annotates documents with SNOMED-style concepts at the document level, linked to text span evidence and structured intermediate reasoning steps.

## Common Commands

### Quick Start (Makefile - Recommended)

```bash
make install       # install all dependencies (backend + frontend)
make run           # build frontend and run production server (single command!)
make dev-backend   # run backend in dev mode (port 8000, hot-reload)
make dev-frontend  # run frontend in dev mode (port 5173)
make test          # run all tests
make test-verbose  # run tests with verbose output
make clean         # remove build artifacts
make help          # show all available commands
```

### Docker (Containerized)

```bash
# Initial setup
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# Start with docker-compose (recommended)
make docker-up              # or: docker compose up -d

# View logs
make docker-logs            # or: docker compose logs -f

# Stop
make docker-down            # or: docker compose down

# Access application
open http://localhost:8000
```

**Requirements:**
- Docker 20.10+ and Docker Compose 2.0+
- SNOMED CT data in `data/terminology/SnomedCT/` (mounted as volume)
- Anthropic API key in `.env` file

**Volume Management:**

Backup data:
```bash
docker run --rm -v textractor-data:/data -v $(pwd):/backup alpine tar czf /backup/textractor-data-backup.tar.gz -C /data .
```

Restore data:
```bash
docker run --rm -v textractor-data:/data -v $(pwd):/backup alpine sh -c "cd /data && tar xzf /backup/textractor-data-backup.tar.gz"
```

**See `docs/DOCKER.md` for comprehensive deployment guide including AWS and GCP.**

### Backend (Manual)

```bash
uv sync                                                     # install/update dependencies

# Run backend (port 8000, hot-reload)
TEXTRACTOR_DOC_ROOT=./data/documents uv run textractor
```

FastAPI interactive docs available at `http://localhost:8000/docs` when running.

### Frontend (Manual)

```bash
cd frontend
npm install        # first time only
npm run dev        # Vite dev server on port 5173 (proxies /api → :8000)
npm run build      # production build → frontend/dist/
```

### Testing

**Backend tests (129 tests):**
```bash
make test                              # run all tests (recommended)
make test-verbose                      # verbose output

# Or use pytest directly:
uv sync --extra dev                    # install test dependencies (pytest)
uv run pytest                          # run all backend tests
uv run pytest tests/test_snomed.py     # run specific test file
uv run pytest -v                       # verbose output
uv run pytest -k "search"              # run tests matching pattern
```

**Frontend tests (29 tests):**
```bash
cd frontend
npm test                               # run all frontend tests (Vitest)
npm test -- --ui                       # run with UI
npm test -- --coverage                 # run with coverage report
npm test -- SpanHighlighter            # run specific test file
```

**Test coverage:**
- **Backend:** Storage layer, routers (documents, annotations, terminology), LLM module
- **Frontend:** Components (SpanHighlighter, ConceptSearch), test infrastructure with Vitest + React Testing Library

**Note:** SNOMED tests require SNOMED CT RF2 files in `data/terminology/SnomedCT/`. Tests will skip if data is not present.

### Dev mode (both together)

**Using Makefile:**
```
Terminal 1: make dev-backend
Terminal 2: make dev-frontend
Browser:    http://localhost:5173
```

**Manual:**
```
Terminal 1: TEXTRACTOR_DOC_ROOT=./data/documents uv run textractor
Terminal 2: cd frontend && npm run dev
Browser:    http://localhost:5173
```

### Production

**Using Makefile (recommended):**
```bash
make run    # builds frontend and starts server in one command
```

**Manual:**
`npm run build` in `frontend/`, then `uv run textractor` — FastAPI auto-serves `frontend/dist/` via `StaticFiles`.

## Architecture

### Backend (`src/textractor/api/`)

| File | Role |
|---|---|
| `models.py` | All Pydantic models: `Span`, `ReasoningStep` (with optional `note` field), `DocumentAnnotation`, `AnnotationFile`, `Document`, `DocumentSummary`, `TerminologyConcept`, `TerminologyInfo` |
| `storage.py` | `DocumentStore`: recursively scans `TEXTRACTOR_DOC_ROOT` for `*.json` docs (document files only, not annotations) |
| `annotation_store.py` | `SQLiteAnnotationStore`: SQLite-based annotation storage with version history and multi-user support. Append-only design with WAL mode for concurrent access. |
| `enhanced_terminology.py` | `EnhancedTerminologyIndex`: SNOMED CT terminology search using SQLite FTS5. Converts SNOMED results to `TerminologyConcept` format. |
| `dependencies.py` | Module-level singletons (`_store`, `_annotation_store`, `_terminology`) initialized in the FastAPI lifespan. Loads SNOMED from `data/terminology/SnomedCT/` if available. |
| `routers/documents.py` | `GET /api/documents`, `POST /api/documents/upload`, `GET /api/documents/{id}`, `PATCH /api/documents/{id}/metadata`, `DELETE /api/documents/{id}`. Uses annotation store for status checks and deletion. |
| `routers/annotations.py` | `GET/PUT /api/documents/{id}/annotations` — PUT validates referential integrity (span/step IDs must exist). Also includes `GET /api/documents/{id}/annotations/history` (version history) and `POST /api/documents/{id}/annotations/revert/{version}` (version rollback). |
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
| `DocumentList` | Project-based organization with collapsible groups. Projects stored in `doc.metadata.project`. Uses "Add Files" dialog to move documents between projects. Export button downloads project as ZIP file. |
| `AnnotationGraph` | React Flow interactive graph showing document annotation → reasoning steps → spans. Nodes are draggable, zoomable, pannable. |

### Data model

Input document (`{doc_id}.json`):
```json
{ "id": "doc_001", "text": "...", "metadata": {} }
```

Annotation format (stored in SQLite):
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

### Annotation Storage

**SQLite-based storage** with version history and multi-user support:

**Architecture:**
- Annotations stored in SQLite database (default: `./data/textractor.db`)
- Append-only version history - every save creates a new version
- Multi-user support via `annotator` parameter (default: "default")
- WAL (Write-Ahead Logging) mode for concurrent read/write access
- JSON blob storage for flexibility

**Features:**
- **Version history**: Every annotation save creates a new version with timestamp
- **Version rollback**: Revert to any previous version via API
- **Multi-user**: Multiple annotators can work on the same document independently
- **Source tracking**: Tracks whether annotations are from "human" or "model" (AI)
- **Model tracking**: Records which model generated AI annotations

**Migration from legacy `.ann.json` files:**

If upgrading from a previous version that used `.ann.json` sidecar files:

```bash
# Dry-run to preview changes
uv run textractor migrate-annotations --dry-run

# Migrate and archive original files
uv run textractor migrate-annotations --archive

# Verbose output
uv run textractor migrate-annotations --archive --verbose
```

**Options:**
- `--dry-run`: Preview what would be migrated without making changes
- `--archive`: Move original `.ann.json` files to `.ann.json.bak` after successful import
- `--annotator NAME`: Set annotator name for imported annotations (default: "default")
- `--verbose`: Show detailed progress

All legacy annotations are imported as version 1 with `source="human"`.

**CLI Export:**

Export a project's documents and annotations to a ZIP file:

```bash
# Export project to default location (./{project-name}.zip)
uv run textractor export-project my-project

# Export to specific location
uv run textractor export-project my-project --output /path/to/backup.zip

# Export with custom annotator
uv run textractor export-project my-project --annotator john_doe

# Verbose output
uv run textractor export-project my-project --verbose
```

**Options:**
- `--output` / `-o` - Output path for ZIP file (default: `./{project-name}.zip`)
- `--annotator` - Annotator name for annotations (default: "default")
- `--doc-root` - Document root directory (default: `$TEXTRACTOR_DOC_ROOT` or `./data/documents`)
- `--db-path` - SQLite database path (default: `$TEXTRACTOR_DB_PATH` or `./data/textractor.db`)
- `--verbose` / `-v` - Enable verbose logging

The exported ZIP contains:
- `{doc_id}.json` - Document files
- `{doc_id}.ann.json` - Annotation files (latest version)

To import, unzip files into `TEXTRACTOR_DOC_ROOT` and run `uv run textractor migrate-annotations` if needed.

### Project Export

**Export projects for backup and collaboration:**

**Features:**
- Export entire project as ZIP file (documents + annotations)
- Export all documents when no project selected
- Annotations exported from SQLite to `.ann.json` format
- ZIP filename matches project name

**Usage:**
- Right-click project → "Export Project"
- Downloads `{project-name}.zip` containing:
  - `{doc_id}.json` - Document files
  - `{doc_id}.ann.json` - Annotation files (latest version)

**API:**
- `GET /api/documents/export?project={name}` - Export specific project
- `GET /api/documents/export` - Export all documents

**Import:**
- Unzip files into `TEXTRACTOR_DOC_ROOT`
- Documents automatically detected on next load
- Annotations imported via: `uv run textractor migrate-annotations`

### Environment variables

#### Server Configuration

| Variable | Default | Description |
|---|---|---|
| `TEXTRACTOR_HOST` | `0.0.0.0` | Server host address |
| `TEXTRACTOR_PORT` | `8000` | Server port |
| `TEXTRACTOR_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated list of allowed CORS origins |

#### Storage Configuration

| Variable | Default | Description |
|---|---|---|
| `TEXTRACTOR_DOC_ROOT` | `./data/documents` | Directory scanned recursively for `*.json` document files |
| `TEXTRACTOR_DB_PATH` | `./data/textractor.db` | SQLite database path for annotation storage with version history |
| `TEXTRACTOR_SNOMED_DIR` | `./data/terminology/SnomedCT` | Directory containing SNOMED CT RF2 files |

#### LLM Configuration

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | (required for pre-annotation) | Anthropic API key for Claude AI access (not needed for Bedrock) |
| `AWS_BEARER_TOKEN_BEDROCK` | - | AWS bearer token for Bedrock authentication (alternative to direct API) |
| `AWS_REGION` | `us-east-1` | AWS region for Bedrock (only used if `AWS_BEARER_TOKEN_BEDROCK` is set) |
| `TEXTRACTOR_LLM_MODEL` | `claude-sonnet-4-5` | Model name for annotation generation (use Bedrock model IDs when using Bedrock) |
| `TEXTRACTOR_LLM_MAX_TOKENS_EXTRACT` | `4096` | Maximum tokens for medical term extraction |
| `TEXTRACTOR_LLM_MAX_TOKENS_ANNOTATE` | `16384` | Maximum tokens for annotation generation |
| `TEXTRACTOR_LLM_TEMPERATURE` | `0.0` | LLM temperature (0.0 = deterministic) |
| `TEXTRACTOR_FUZZY_THRESHOLD` | `90` | Minimum similarity (0-100) for span offset recovery |

**LLM Provider Options:**
- **Direct Anthropic API (default):** Set `ANTHROPIC_API_KEY` only
- **AWS Bedrock:** Set `AWS_BEARER_TOKEN_BEDROCK` (and optionally `AWS_REGION`). When using Bedrock, use Bedrock model IDs like `anthropic.claude-sonnet-4-0-v1` for `TEXTRACTOR_LLM_MODEL`.

**SNOMED CT Setup:**
- Place SNOMED CT RF2 files in `data/terminology/SnomedCT/` (or path specified in `TEXTRACTOR_SNOMED_DIR`)
- SQLite database will be automatically built at `data/terminology/snomed.db` on first startup
- Subsequent startups will reuse the existing database

- When working on a github issue, create a new, appropriately named local branch. Do the work on that branch, then push to remote and create a Pull Request linked to the issue.