# Textractor

A clinical text annotation tool for creating structured, evidence-linked concept annotations. Annotators select text spans as evidence, build intermediate reasoning steps, and assign final document-level codes — all linked to each other.

Built with FastAPI + React.

---

## 🐳 Quick Start with Docker

```bash
# One-time setup
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY

# docker compose automatically reads .env

# Start application
docker compose up -d

# Access at http://localhost:8000
```

See [Docker Deployment Guide](docs/DOCKER.md) for comprehensive instructions.

## Prerequisites

**Native Installation:**
- Python 3.10+
- Node.js 20+
- uv package manager

**Docker (Recommended):**
- Docker 20.10+
- Docker Compose 2.0+

---

## Quickstart

### Single-Command Setup (Recommended)

```bash
# 1. Install dependencies
make install

# 2. Create a documents directory and add some documents
mkdir -p data/documents
cp my_notes/*.json data/documents/

# 3. Build and run (production mode - single command!)
make run

# Open http://localhost:8000
```

### Development Mode (Two Terminals)

```bash
# Terminal 1: Backend with hot-reload
make dev-backend

# Terminal 2: Frontend with hot-reload
make dev-frontend

# Open http://localhost:5173
```

### Manual Setup (Alternative)

```bash
# 1. Install backend dependencies
uv sync

# 2. Install frontend dependencies
cd frontend && npm install && cd ..

# 3. Create a documents directory and add some documents
mkdir -p data/documents
cp my_notes/*.json data/documents/

# 4. Build frontend
cd frontend && npm run build && cd ..

# 5. Start the backend (serves built frontend)
TEXTRACTOR_DOC_ROOT=./data/documents uv run textractor

# textractor automatically loads .env when started from the project root

# Open http://localhost:8000
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

## Terminology Search

Textractor supports two clinical terminology systems for concept search. Both use SQLite FTS5 (full-text search) with trigram tokenization and custom relevance scoring. When multiple systems are loaded, a **terminology selector dropdown** appears in the annotation panel.

### SNOMED CT

1. Download SNOMED CT RF2 files from [SNOMED International](https://www.snomed.org/snomed-ct/get-snomed)
2. Place them in `data/terminology/SnomedCT/`
3. On first startup, Textractor builds a searchable SQLite database at `data/terminology/snomed.db`
4. Subsequent startups reuse the existing database (instant load)

**Characteristics:**
- ~2.6M descriptions, ~50MB RAM footprint
- Hierarchical clinical concepts with rich synonyms

### ICD-10-CM

1. Download the CMS ICD-10-CM flat file from [CMS ICD-10 codes](https://www.cms.gov/medicare/coding-billing/icd-10-codes)
   - Look for the "Code Descriptions in Tabular Order" ZIP — the file inside is named `icd10cm_codes_YYYY.txt`
2. Place it at `data/terminology/icd10cm_codes.txt` (or set `TEXTRACTOR_ICD10CM_FILE`)
3. On first startup, Textractor builds a searchable SQLite database at `data/terminology/icd10cm.db`
4. Subsequent startups reuse the existing database (instant load)

**Characteristics:**
- ~78,000 billable codes with plain-English descriptions
- Ideal for final coding assignments
- File format: space-separated, no header, one code per line

### Common Features

- **Persistent storage**: Database built once, instant subsequent startups
- **Fast full-text search**: FTS5 trigram tokenization for substring matching
- **Smart ranking**: Multi-factor scoring (exact match, prefix, word boundary, position)
- **Deduplication**: One result per code/concept ID

If neither terminology system is available, the concept search fields will be empty.

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

### AI Pre-Annotation

Click **✨ Pre-annotate** to generate AI annotations using Claude. The system:
- Extracts medical terms from the document
- Searches SNOMED CT for relevant concepts
- Generates structured annotations (spans → reasoning steps → document annotations)
- Filters to clinical concepts only (problems, procedures, medications, labs, symptoms, etc.)
- Enforces strict hierarchy (every annotation traces back through reasoning steps to text evidence)

AI-generated content is marked with ✨ badges and loads as unsaved changes for review. Make any edit to trigger auto-save, or click **Revert** to discard.

Annotations are **automatically saved** as you work (2-second debounce). Click **Revert** to discard unsaved changes. Click **🗑️ Clear All** to delete all annotations with confirmation.

### UI Features

- **✨ AI Pre-Annotation** — Generate structured annotations automatically using Claude
  - Extracts clinical concepts and creates evidence-linked annotations
  - Filters to clinical categories (problems, procedures, medications, labs, etc.)
  - AI-generated content marked with ✨ badges
  - Loads as unsaved changes for manual review
- **Auto-Save** — Annotations save automatically after you stop editing
- **🗑️ Clear All** — Delete all annotations with confirmation dialog
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
| `POST` | `/api/documents/{id}/preannotate` | Generate AI annotations using Claude (requires `ANTHROPIC_API_KEY`) |
| `GET` | `/api/terminology/search?q=&limit=&system=` | Search terminology concepts (`system`: `SNOMED-CT` or `ICD-10-CM`, default `SNOMED-CT`) |
| `GET` | `/api/terminology/info` | Terminology load status, loaded systems, and concept counts |

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
│   └── terminology/      # Terminology SQLite search
│       ├── snomed.py     # SNOMED CT FTS5 implementation
│       └── icd10cm.py    # ICD-10-CM FTS5 implementation
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
    └── terminology/         # Terminology files
        ├── SnomedCT/        # Place SNOMED CT RF2 files here
        ├── snomed.db        # Auto-generated SQLite database
        ├── icd10cm_codes.txt  # CMS ICD-10-CM flat file (download separately)
        └── icd10cm.db       # Auto-generated SQLite database
```

---

## Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `TEXTRACTOR_DOC_ROOT` | `./data/documents` | Directory scanned recursively for `*.json` documents |
| `TEXTRACTOR_DB_PATH` | `./data/textractor.db` | SQLite database for annotation storage |
| `TEXTRACTOR_SNOMED_DIR` | `./data/terminology/SnomedCT` | Directory containing SNOMED CT RF2 files |
| `TEXTRACTOR_ICD10CM_FILE` | `./data/terminology/icd10cm_codes.txt` | Path to CMS ICD-10-CM flat file |
| `ANTHROPIC_API_KEY` | *(required for AI)* | API key for Claude AI pre-annotation |
| `TEXTRACTOR_LLM_MODEL` | `claude-sonnet-4-5` | Model name for AI annotation generation |
| `TEXTRACTOR_FUZZY_THRESHOLD` | `90` | Minimum similarity (0-100) for span offset recovery |

Terminology systems are loaded automatically at startup if their files/directories exist.

---

## Testing

```bash
# Install test dependencies
uv sync --extra dev

# Run all tests
make test

# Run with verbose output
make test-verbose

# Or use pytest directly
uv run pytest tests/test_annotations.py
uv run pytest -k "lock"
```

**Test Coverage:**
- Annotation API (create, edit, lock/unlock)
- SNOMED CT search (build index, search, ranking, persistence)
- Document locking enforcement
- Referential integrity validation

---

## Production Deployment

### Using Makefile (Recommended)

```bash
# Single command - builds frontend and starts server
make run

# Or with custom document directory
DOC_ROOT=/path/to/documents make run
```

### Manual

```bash
# Build the frontend
cd frontend && npm run build && cd ..

# Run — FastAPI serves the React app at /
TEXTRACTOR_DOC_ROOT=/path/to/documents uv run textractor
```

The app is then available at `http://localhost:8000`.

For terminology support, ensure files are in place before first startup:
- **SNOMED CT**: RF2 files in `data/terminology/SnomedCT/`
- **ICD-10-CM**: CMS flat file at `data/terminology/icd10cm_codes.txt`

### Available Make Commands

Run `make help` to see all available commands:
- `make install` - Install all dependencies
- `make build` - Build frontend only
- `make run` - Build and run production server
- `make dev-backend` - Run backend in dev mode
- `make dev-frontend` - Run frontend in dev mode
- `make test` - Run tests
- `make clean` - Remove build artifacts

---

## Recent Features

- ✅ **AI Pre-Annotation** - Generate structured annotations automatically using Claude
- ✅ **Clinical Filtering** - AI annotations filtered to clinical concepts only
- ✅ **Hierarchy Enforcement** - Strict evidence traceability (spans → steps → annotations)
- ✅ **Clear All Button** - Delete all annotations with confirmation
- ✅ **ICD-10-CM Integration** - Full-text search across ~78,000 billable codes with terminology selector dropdown
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
