# Textractor

A clinical text annotation tool for creating structured, evidence-linked concept annotations. Annotators select text spans as evidence, build intermediate reasoning steps, and assign final document-level codes — all linked to each other.

Built with FastAPI + React.

---

## Quickstart

```bash
# 1. Install backend dependencies
uv sync

# 2. Install frontend dependencies
cd frontend && npm install && cd ..

# 3. Create a documents directory and add some documents
mkdir -p data/documents
cp my_notes/*.json data/documents/

# 4. Start the backend
TEXTRACTOR_DOC_ROOT=./data/documents uv run textractor

# 5. In a second terminal, start the frontend
cd frontend && npm run dev

# Open http://localhost:5173
```

---

## Document Format

Input documents are JSON files. The only required fields are `id` and `text`:

```json
{
  "id": "note_001",
  "text": "68-year-old male presenting with acute chest pain radiating to the left arm. ECG shows ST elevation in leads II, III, and aVF. Troponin I elevated at 4.2 ng/mL. History of hypertension and hyperlipidemia.",
  "metadata": {
    "patient_id": "PT-8842",
    "date": "2024-03-15",
    "note_type": "ED Admission"
  }
}
```

The `metadata` field is optional and can contain any key-value pairs. Place these files in the directory pointed to by `TEXTRACTOR_DOC_ROOT`.

---

## SNOMED CT Terminology

Textractor uses **SNOMED CT** for clinical terminology search via SQLite FTS5 (full-text search).

### Setup

1. Download SNOMED CT RF2 files
2. Place them in `data/terminology/SnomedCT/`
3. On first startup, Textractor automatically builds a searchable SQLite database at `data/terminology/snomed.db`
4. Subsequent startups reuse the existing database (instant load)

### Features

- **Persistent storage**: Database built once, ~50MB RAM footprint
- **Fast full-text search**: FTS5 with trigram tokenization for substring matching
- **2.6M+ SNOMED descriptions**: Comprehensive clinical vocabulary
- **Smart ranking**: Multi-factor scoring (exact match, prefix, word boundary, position)
- **Deduplication**: One result per concept ID

If SNOMED CT is not available, the terminology search will be empty.

---

## Annotation Workflow

Each document supports three layers of annotation that reference each other:

```
Text spans  →  Reasoning steps  →  Document annotations
(evidence)     (intermediate)       (final code)
```

**1. Create spans** — Select text in the document viewer. Each selection becomes a named span with character offsets.

**2. Create reasoning steps** — Search for an intermediate concept (e.g. "ST elevation MI pattern"), then check which spans support it. Reasoning steps capture the inferential path from evidence to conclusion. Optionally add free-form notes to document your reasoning.

**3. Create document annotations** — Search for the final code (e.g. "Acute myocardial infarction"), link it to evidence spans and the reasoning steps that led to it. Click on a document annotation to view its interactive evidence graph.

Annotations are **automatically saved** as you work (2-second debounce). Click **Revert** to discard unsaved changes.

### UI Features

- **Auto-Save** — Annotations save automatically after you stop editing
- **Document Locking** — Mark documents as "Completed" to prevent accidental modifications
  - Lock icon (🔒) displayed when completed
  - All editing disabled with clear visual feedback
  - Uncheck "Completed" to unlock and resume editing
- **Project Organization** — Group documents into collapsible projects in the left sidebar
- **Interactive Graph** — Visualize document annotations with their linked reasoning steps and evidence spans
- **Annotation Highlighting** — Click document annotations to highlight and filter related evidence
- **Resizable Panels** — Drag panel borders to adjust workspace layout
- **Font Size Control** — Use +/- buttons to adjust document text size
- **Filter & Search** — Filter by annotated/unannotated/completed status

---

## Annotation Output Format

Each document gets a companion `.ann.json` file saved alongside it:

```json
{
  "doc_id": "note_001",
  "completed": false,
  "spans": [
    {
      "id": "span_a3f2b1c0",
      "start": 43,
      "end": 72,
      "text": "acute chest pain radiating to the left arm"
    },
    {
      "id": "span_d9e4f820",
      "start": 74,
      "end": 121,
      "text": "ECG shows ST elevation in leads II, III, and aVF"
    },
    {
      "id": "span_c1a2e391",
      "start": 123,
      "end": 154,
      "text": "Troponin I elevated at 4.2 ng/mL"
    }
  ],
  "reasoning_steps": [
    {
      "id": "step_7b3f9d12",
      "concept": {
        "code": "401303003",
        "display": "Acute ST-segment elevation myocardial infarction",
        "system": "SNOMED-CT"
      },
      "span_ids": [
        "span_d9e4f820",
        "span_c1a2e391"
      ],
      "note": "ECG findings combined with elevated troponin indicate acute STEMI"
    }
  ],
  "document_annotations": [
    {
      "id": "ann_5e2a1f88",
      "concept": {
        "code": "57054005",
        "display": "Acute myocardial infarction",
        "system": "SNOMED-CT"
      },
      "evidence_span_ids": [
        "span_a3f2b1c0",
        "span_d9e4f820",
        "span_c1a2e391"
      ],
      "reasoning_step_ids": [
        "step_7b3f9d12"
      ],
      "note": ""
    }
  ]
}
```

---

## API

The backend exposes a REST API documented interactively at `http://localhost:8000/docs`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/documents` | List all documents with annotation status |
| `POST` | `/api/documents/upload` | Upload a document JSON file |
| `GET` | `/api/documents/{id}` | Get document text and metadata |
| `PATCH` | `/api/documents/{id}/metadata` | Update document metadata (e.g., project) |
| `DELETE` | `/api/documents/{id}` | Delete a document and its annotations |
| `GET` | `/api/documents/{id}/annotations` | Get current annotations (empty structure if none) |
| `PUT` | `/api/documents/{id}/annotations` | Save annotations (validates all ID references, enforces locks) |
| `GET` | `/api/terminology/search?q=&limit=` | Search SNOMED CT concepts by full-text query |
| `GET` | `/api/terminology/info` | Terminology load status and concept count |

### Document Locking

The `PUT /api/documents/{id}/annotations` endpoint enforces document locking:
- Returns `403 Forbidden` if document is marked as completed
- Allows unchecking the `completed` flag to unlock
- Prevents accidental modifications to finalized annotations

### Example: batch-upload documents via API

```bash
for f in data/documents/*.json; do
  curl -s -F "file=@$f" http://localhost:8000/api/documents/upload
done
```

### Example: export all annotations

```bash
# All .ann.json files in the document root are the annotation output
find data/documents -name "*.ann.json" | sort
```

---

## Project Structure

```
textractor/
├── src/textractor/
│   ├── api/              # FastAPI backend
│   │   ├── models.py     # Pydantic data models
│   │   ├── storage.py    # Document store
│   │   ├── enhanced_terminology.py # SNOMED CT search wrapper
│   │   ├── dependencies.py # Dependency injection
│   │   ├── routers/      # API endpoints
│   │   │   ├── documents.py
│   │   │   ├── annotations.py
│   │   │   └── terminology.py
│   │   └── main.py       # App factory
│   └── terminology/      # SNOMED CT SQLite search
│       └── snomed.py     # FTS5 implementation
├── frontend/             # React + TypeScript UI
│   ├── src/
│   │   ├── components/   # UI components
│   │   ├── hooks/        # Custom React hooks
│   │   ├── utils/        # Shared utilities
│   │   ├── api/          # API client
│   │   └── types/        # TypeScript interfaces
│   └── dist/             # Production build output
├── tests/                # Backend tests (pytest)
│   ├── test_annotations.py     # Annotation API tests
│   ├── test_snomed.py          # SNOMED search tests
│   ├── test_deduplication.py   # Search result tests
│   └── test_terminology_integration.py
└── data/
    ├── documents/        # Document storage (.json + .ann.json)
    └── terminology/      # SNOMED CT RF2 files
        ├── SnomedCT/     # Place RF2 files here
        └── snomed.db     # Auto-generated SQLite database
```

---

## Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `TEXTRACTOR_DOC_ROOT` | `./data/documents` | Directory scanned recursively for `*.json` documents |

SNOMED CT is automatically loaded from `data/terminology/SnomedCT/` if present.

---

## Testing

```bash
# Install test dependencies
uv sync --extra dev

# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_annotations.py

# Run with verbose output
uv run pytest -v

# Run tests matching a pattern
uv run pytest -k "lock"
```

**Test Coverage:**
- Annotation API (create, edit, lock/unlock)
- SNOMED CT search (build index, search, ranking, persistence)
- Document locking enforcement
- Referential integrity validation

---

## Production Deployment

```bash
# Build the frontend
cd frontend && npm run build && cd ..

# Run — FastAPI serves the React app at /
TEXTRACTOR_DOC_ROOT=/path/to/documents uv run textractor
```

The app is then available at `http://localhost:8000`.

For SNOMED CT support, ensure RF2 files are in `data/terminology/SnomedCT/` before first startup.

---

## Recent Features

- ✅ **SNOMED CT Integration** - Full-text search across 2.6M+ clinical concepts
- ✅ **SQLite FTS5** - Persistent, low-memory terminology search
- ✅ **Auto-Save** - Annotations save automatically with revert capability
- ✅ **Document Locking** - Prevent edits to completed documents
- ✅ **Project Organization** - Group and filter documents by project
- ✅ **Interactive Graph** - Visualize annotation relationships
- ✅ **Enhanced UX** - Resizable panels, font controls, smart highlighting

---

## License

See LICENSE file.
