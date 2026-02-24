# Bulk Project Export Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable users to export all documents and annotations in a project as a downloadable ZIP file for backup and collaboration.

**Architecture:** Add backend endpoint that queries documents by project, exports annotations from SQLite to JSON format, creates ZIP file with both documents and annotations, and streams to client. Frontend adds export button to project menu.

**Tech Stack:** Python zipfile module, FastAPI streaming response, React fetch with blob download

---

## Task 1: Backend Export Endpoint (Router)

**Files:**
- Modify: `src/textractor/api/routers/documents.py`
- Test: `tests/test_export.py` (create)

**Step 1: Write the failing test**

Create `tests/test_export.py`:

```python
"""Tests for project export functionality."""
import io
import json
import tempfile
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from textractor.api.main import create_app
from textractor.api.dependencies import init_annotation_store, init_store, init_terminology
from textractor.api.models import Document, AnnotationFile, Span


@pytest.fixture
def client_with_project():
    """Create a test client with a project containing documents and annotations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        doc_root = Path(tmpdir)

        # Create documents in test-project
        doc1 = doc_root / "doc_001.json"
        doc1.write_text(json.dumps({
            "id": "doc_001",
            "text": "First document",
            "metadata": {"project": "test-project"}
        }))

        doc2 = doc_root / "doc_002.json"
        doc2.write_text(json.dumps({
            "id": "doc_002",
            "text": "Second document",
            "metadata": {"project": "test-project"}
        }))

        # Create document in different project
        doc3 = doc_root / "doc_003.json"
        doc3.write_text(json.dumps({
            "id": "doc_003",
            "text": "Other project",
            "metadata": {"project": "other-project"}
        }))

        # Initialize app
        init_store(doc_root)
        init_annotation_store(doc_root / "test.db")
        init_terminology(snomed_dir=None)

        # Add annotations for doc_001
        from textractor.api.dependencies import get_annotation_store
        ann_store = get_annotation_store()
        ann_store.save_annotations(
            doc_id="doc_001",
            annotations=AnnotationFile(
                doc_id="doc_001",
                spans=[Span(id="span_1", start=0, end=5, text="First")],
                reasoning_steps=[],
                document_annotations=[],
                completed=False,
            ),
            annotator="default",
            source="human",
        )

        app = create_app()
        yield TestClient(app)


def test_export_project_returns_zip(client_with_project):
    """Test that exporting a project returns a ZIP file."""
    response = client_with_project.get("/api/documents/export?project=test-project")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
    assert "test-project" in response.headers["content-disposition"]


def test_export_project_contains_documents(client_with_project):
    """Test that exported ZIP contains document JSON files."""
    response = client_with_project.get("/api/documents/export?project=test-project")

    zip_data = io.BytesIO(response.content)
    with zipfile.ZipFile(zip_data, 'r') as zf:
        files = zf.namelist()
        assert "doc_001.json" in files
        assert "doc_002.json" in files
        assert "doc_003.json" not in files  # Different project

        # Verify document content
        doc1_content = json.loads(zf.read("doc_001.json"))
        assert doc1_content["id"] == "doc_001"
        assert doc1_content["text"] == "First document"


def test_export_project_contains_annotations(client_with_project):
    """Test that exported ZIP contains annotation JSON files."""
    response = client_with_project.get("/api/documents/export?project=test-project")

    zip_data = io.BytesIO(response.content)
    with zipfile.ZipFile(zip_data, 'r') as zf:
        files = zf.namelist()
        assert "doc_001.ann.json" in files

        # Verify annotation content
        ann_content = json.loads(zf.read("doc_001.ann.json"))
        assert ann_content["doc_id"] == "doc_001"
        assert len(ann_content["spans"]) == 1
        assert ann_content["spans"][0]["text"] == "First"


def test_export_all_documents(client_with_project):
    """Test exporting all documents when no project specified."""
    response = client_with_project.get("/api/documents/export")

    assert response.status_code == 200

    zip_data = io.BytesIO(response.content)
    with zipfile.ZipFile(zip_data, 'r') as zf:
        files = zf.namelist()
        assert "doc_001.json" in files
        assert "doc_002.json" in files
        assert "doc_003.json" in files


def test_export_nonexistent_project(client_with_project):
    """Test exporting a project that doesn't exist."""
    response = client_with_project.get("/api/documents/export?project=nonexistent")

    assert response.status_code == 200  # Empty ZIP is valid

    zip_data = io.BytesIO(response.content)
    with zipfile.ZipFile(zip_data, 'r') as zf:
        assert len(zf.namelist()) == 0
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_export.py -v`

Expected: FAIL with "404 Not Found" (endpoint doesn't exist yet)

**Step 3: Write minimal implementation**

In `src/textractor/api/routers/documents.py`, add at the end:

```python
import io
import zipfile
from fastapi.responses import StreamingResponse


@router.get("/export")
def export_project(
    project: str | None = None,
    annotator: str = "default",
    doc_store: DocumentStore = Depends(get_store),
    ann_store: SQLiteAnnotationStore = Depends(get_annotation_store),
):
    """Export documents and annotations as a ZIP file.

    Args:
        project: Project name to export. If None, exports all documents.
        annotator: Annotator name for annotations (default: "default")

    Returns:
        ZIP file containing document JSON files and annotation JSON files.
    """
    # Get all documents
    all_docs = doc_store.list_documents()

    # Filter by project if specified
    if project is not None:
        docs_to_export = [
            d for d in all_docs
            if d.metadata.get("project") == project
        ]
    else:
        docs_to_export = all_docs

    # Create ZIP in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for doc_summary in docs_to_export:
            # Add document JSON
            doc = doc_store.get_document(doc_summary.id)
            if doc:
                doc_json = doc.model_dump_json(indent=2)
                zf.writestr(f"{doc.id}.json", doc_json)

            # Add annotations JSON if they exist
            annotations = ann_store.get_annotations(doc_summary.id, annotator=annotator)
            if annotations:
                ann_json = annotations.model_dump_json(indent=2)
                zf.writestr(f"{doc_summary.id}.ann.json", ann_json)

    # Prepare response
    zip_buffer.seek(0)
    filename = f"{project or 'all-documents'}.zip"

    return StreamingResponse(
        io.BytesIO(zip_buffer.read()),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_export.py -v`

Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/textractor/api/routers/documents.py tests/test_export.py
git commit -m "feat: add backend endpoint for project export (Issue #80)"
```

---

## Task 2: Frontend Export Button (UI)

**Files:**
- Modify: `frontend/src/components/DocumentList.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/index.css`

**Step 1: Add API client method**

In `frontend/src/api/client.ts`, add to the `api` object:

```typescript
exportProject: (projectName: string | null) => {
  const params = projectName ? `?project=${encodeURIComponent(projectName)}` : '';
  return fetch(`${API_BASE}/documents/export${params}`)
    .then(res => {
      if (!res.ok) throw new Error(`Export failed: ${res.statusText}`);
      return res.blob();
    })
    .then(blob => {
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${projectName || 'all-documents'}.zip`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    });
},
```

**Step 2: Add export button to project menu**

In `frontend/src/components/DocumentList.tsx`, add state for export loading:

```typescript
const [exportingProject, setExportingProject] = useState<string | null>(null);
```

Find the project menu buttons section (around line 505) and add export button after "Add Files":

```typescript
<button
  className="project-menu-item"
  onClick={async (e) => {
    e.stopPropagation();
    setShowProjectMenu(null);
    setExportingProject(project);
    try {
      await api.exportProject(project === 'Uncategorized' ? null : project);
    } catch (err) {
      setUploadError(`Failed to export project: ${err}`);
    } finally {
      setExportingProject(null);
    }
  }}
  disabled={exportingProject === project}
>
  {exportingProject === project ? '📦 Exporting...' : '📦 Export Project'}
</button>
```

**Step 3: Add CSS styling**

In `frontend/src/index.css`, add styles for the export button:

```css
.project-menu-item:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
```

**Step 4: Manual test**

1. Start backend: `make dev-backend`
2. Start frontend: `make dev-frontend`
3. Navigate to http://localhost:5173
4. Right-click on a project → Click "Export Project"
5. Verify ZIP file downloads with correct name
6. Extract ZIP and verify contents

Expected: ZIP file downloads containing document and annotation JSON files

**Step 5: Commit**

```bash
git add frontend/src/components/DocumentList.tsx frontend/src/api/client.ts frontend/src/index.css
git commit -m "feat: add export button to project menu (Issue #80)"
```

---

## Task 3: Documentation

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Add export documentation**

In `CLAUDE.md`, find the "### Frontend" section and update the DocumentList description:

```markdown
| `DocumentList` | Project-based organization with collapsible groups. Projects stored in `doc.metadata.project`. Uses "Add Files" dialog to move documents between projects. Export button downloads project as ZIP file. |
```

Add new section after "### Annotation Storage":

```markdown
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
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add project export documentation (Issue #80)"
```

---

## Task 4: Integration Testing

**Files:**
- Test: Manual integration test

**Step 1: Create test project with annotations**

1. Start application
2. Create a new project "Export Test"
3. Upload 2-3 documents to the project
4. Add annotations to at least one document
5. Mark one document as completed

**Step 2: Export and verify**

1. Right-click "Export Test" project
2. Click "Export Project"
3. Verify `Export Test.zip` downloads
4. Extract ZIP to temporary directory
5. Verify all document JSON files present
6. Verify annotation files present for annotated documents
7. Verify annotation files have correct structure

**Step 3: Test import workflow**

1. Delete the project from the application
2. Copy extracted files to `data/documents/`
3. Refresh browser
4. Verify documents appear
5. Run: `uv run textractor migrate-annotations --dry-run`
6. Verify annotations detected
7. Run: `uv run textractor migrate-annotations`
8. Verify annotations restored

Expected: Full export → import → restore cycle works correctly

**Step 4: Commit**

```bash
git commit --allow-empty -m "test: verify export/import workflow (Issue #80)"
```

---

## Task 5: Create Pull Request

**Files:**
- None (Git operations)

**Step 1: Push branch**

```bash
git push -u origin feature/issue-80-project-export
```

**Step 2: Create PR**

```bash
gh pr create --title "feat: add bulk project export (Issue #80)" --body "$(cat <<'EOF'
Closes #80

## Summary

Adds ability to export entire projects as ZIP files for backup and collaboration.

## Features

**Backend:**
- `GET /api/documents/export?project={name}` endpoint
- Streams ZIP file with documents + annotations
- Exports annotations from SQLite to `.ann.json` format
- Supports exporting all documents (no project filter)

**Frontend:**
- "Export Project" button in project menu
- Downloads ZIP with project name
- Loading state during export
- Error handling

**Import Workflow:**
- Unzip files to `TEXTRACTOR_DOC_ROOT`
- Documents auto-detected
- Annotations imported via migration CLI

## Testing

- 6 backend tests covering:
  - ZIP file generation
  - Document filtering by project
  - Annotation export
  - Empty projects
  - All documents export
- Manual integration testing

## Documentation

Updated CLAUDE.md with:
- Export feature overview
- API endpoints
- Import workflow

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Step 3: Verify PR created**

Run: `gh pr view --web`

Expected: PR opens in browser with correct title and description

---

## Summary

**Implementation checklist:**
- [x] Backend export endpoint with ZIP generation
- [x] SQLite annotation export to JSON format
- [x] Frontend export button in project menu
- [x] API client method with blob download
- [x] CSS styling for export button
- [x] Comprehensive test coverage (6 tests)
- [x] Documentation in CLAUDE.md
- [x] Integration testing
- [x] Pull request creation

**Total effort:** ~2-3 hours
**Files changed:** 5 files
**Tests added:** 6 tests
**Lines of code:** ~250 lines
