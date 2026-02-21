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

## Terminology File

Load a concept vocabulary via a tab-separated file with a header row:

```
code	display	system
57054005	Acute myocardial infarction	SNOMED-CT
194828000	Angina pectoris	SNOMED-CT
44054006	Type 2 diabetes mellitus	SNOMED-CT
38341003	Hypertensive disorder	SNOMED-CT
55822004	Hyperlipidemia	SNOMED-CT
13213009	Congenital heart disease	SNOMED-CT
```

Pass this file at startup:

```bash
TEXTRACTOR_DOC_ROOT=./data/documents \
  TEXTRACTOR_TERMINOLOGY_PATH=./data/concepts.tsv \
  uv run textractor
```

You can also upload or replace the terminology at runtime via the UI or the API (`POST /api/terminology/upload`).

---

## Annotation Workflow

Each document supports three layers of annotation that reference each other:

```
Text spans  →  Reasoning steps  →  Document annotations
(evidence)     (intermediate)       (final code)
```

**1. Create spans** — Select text in the document viewer. Each selection becomes a named span with character offsets.

**2. Create reasoning steps** — Search for an intermediate concept (e.g. "ST elevation MI pattern"), then check which spans support it. Reasoning steps capture the inferential path from evidence to conclusion.

**3. Create document annotations** — Search for the final code (e.g. "Acute myocardial infarction"), link it to evidence spans and the reasoning steps that led to it.

Hit **Save** to write the annotation file to disk.

---

## Annotation Output Format

Each document gets a companion `.ann.json` file saved alongside it:

```json
{
  "doc_id": "note_001",
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
      ]
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
      ]
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
| `GET` | `/api/documents/{id}/annotations` | Get current annotations (empty structure if none) |
| `PUT` | `/api/documents/{id}/annotations` | Save annotations (validates all ID references) |
| `GET` | `/api/terminology/search?q=&limit=` | Search concepts by substring |
| `GET` | `/api/terminology/info` | Terminology load status and count |
| `POST` | `/api/terminology/upload` | Replace the loaded terminology with a new TSV |

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

## Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `TEXTRACTOR_DOC_ROOT` | `./data/documents` | Directory scanned for `*.json` documents |
| `TEXTRACTOR_TERMINOLOGY_PATH` | *(none)* | TSV terminology file loaded at startup |

---

## Production Deployment

```bash
# Build the frontend
cd frontend && npm run build && cd ..

# Run — FastAPI serves the React app at /
TEXTRACTOR_DOC_ROOT=/path/to/documents \
  TEXTRACTOR_TERMINOLOGY_PATH=/path/to/concepts.tsv \
  uv run textractor
```

The app is then available at `http://localhost:8000`.
