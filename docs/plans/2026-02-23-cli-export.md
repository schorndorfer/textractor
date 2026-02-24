# CLI Export Command Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a CLI command to export project documents and annotations as ZIP files, matching GUI functionality.

**Architecture:** Extract shared ZIP creation logic from the API endpoint into `export_utils.py`, then create a standalone CLI command in `cli/export.py` that uses this shared logic. The CLI will work independently of the running server.

**Tech Stack:** Python argparse, zipfile, pathlib, FastAPI (refactored), pytest

---

## Task 1: Create Shared Export Utility

**Files:**
- Create: `src/textractor/api/export_utils.py`
- Test: `tests/test_export_utils.py`

**Step 1: Write failing test for export utility**

Create `tests/test_export_utils.py`:

```python
"""Tests for shared export utilities."""
import io
import json
import tempfile
import zipfile
from pathlib import Path

import pytest

from textractor.api.export_utils import create_export_zip
from textractor.api.storage import DocumentStore
from textractor.api.annotation_store import SQLiteAnnotationStore
from textractor.api.models import Document, DocumentSummary, AnnotationFile, Span


@pytest.fixture
def test_stores():
    """Create test document and annotation stores."""
    with tempfile.TemporaryDirectory() as tmpdir:
        doc_root = Path(tmpdir)

        # Create test documents
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

        # Initialize stores
        doc_store = DocumentStore(doc_root)
        ann_store = SQLiteAnnotationStore(doc_root / "test.db")

        # Add annotations for doc_001
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

        yield doc_store, ann_store


def test_create_export_zip_with_documents_and_annotations(test_stores):
    """Test that create_export_zip generates a valid ZIP with docs and annotations."""
    doc_store, ann_store = test_stores

    # Get documents to export
    all_docs = doc_store.list_documents()
    docs_to_export = [d for d in all_docs if d.metadata.get("project") == "test-project"]

    # Create ZIP
    zip_bytes = create_export_zip(docs_to_export, doc_store, ann_store, annotator="default")

    # Verify it's valid ZIP bytes
    assert isinstance(zip_bytes, bytes)
    assert len(zip_bytes) > 0

    # Verify ZIP contents
    zip_data = io.BytesIO(zip_bytes)
    with zipfile.ZipFile(zip_data, 'r') as zf:
        files = zf.namelist()

        # Should contain both documents
        assert "doc_001.json" in files
        assert "doc_002.json" in files

        # Should contain annotations for doc_001
        assert "doc_001.ann.json" in files

        # Verify document content
        doc1_content = json.loads(zf.read("doc_001.json"))
        assert doc1_content["id"] == "doc_001"

        # Verify annotation content
        ann1_content = json.loads(zf.read("doc_001.ann.json"))
        assert ann1_content["doc_id"] == "doc_001"
        assert len(ann1_content["spans"]) == 1


def test_create_export_zip_empty_list(test_stores):
    """Test that create_export_zip handles empty document list."""
    doc_store, ann_store = test_stores

    # Create ZIP with no documents
    zip_bytes = create_export_zip([], doc_store, ann_store)

    # Should still be valid ZIP
    assert isinstance(zip_bytes, bytes)

    zip_data = io.BytesIO(zip_bytes)
    with zipfile.ZipFile(zip_data, 'r') as zf:
        assert len(zf.namelist()) == 0
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_export_utils.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'textractor.api.export_utils'"

**Step 3: Write minimal implementation**

Create `src/textractor/api/export_utils.py`:

```python
"""Shared utilities for exporting documents and annotations."""
from __future__ import annotations

import io
import logging
import zipfile

from .annotation_store import SQLiteAnnotationStore
from .models import DocumentSummary
from .storage import DocumentStore

logger = logging.getLogger(__name__)


def create_export_zip(
    docs_to_export: list[DocumentSummary],
    doc_store: DocumentStore,
    ann_store: SQLiteAnnotationStore,
    annotator: str = "default",
) -> bytes:
    """Create ZIP file containing documents and annotations.

    Args:
        docs_to_export: List of document summaries to export
        doc_store: Document store instance
        ann_store: Annotation store instance
        annotator: Annotator name for annotations (default: "default")

    Returns:
        ZIP file as bytes
    """
    # Create ZIP in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for doc_summary in docs_to_export:
            # Add document JSON
            doc = doc_store.get_document(doc_summary.id)
            if doc:
                doc_json = doc.model_dump_json(indent=2)
                zf.writestr(f"{doc.id}.json", doc_json)
            else:
                logger.warning(f"Failed to load document {doc_summary.id} for export")

            # Add annotations JSON if they exist
            annotations = ann_store.get_annotations(doc_summary.id, annotator=annotator)
            if annotations:
                ann_json = annotations.model_dump_json(indent=2)
                zf.writestr(f"{doc_summary.id}.ann.json", ann_json)

    # Return bytes
    zip_buffer.seek(0)
    return zip_buffer.read()
```

**Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_export_utils.py -v
```

Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add src/textractor/api/export_utils.py tests/test_export_utils.py
git commit -m "feat: add shared export utility for ZIP creation"
```

---

## Task 2: Refactor API Endpoint to Use Shared Logic

**Files:**
- Modify: `src/textractor/api/routers/documents.py:95-150`
- Test: `tests/test_export.py` (verify existing tests still pass)

**Step 1: Refactor API endpoint**

Modify `src/textractor/api/routers/documents.py`:

```python
# Add import at top
from ..export_utils import create_export_zip

# Replace lines 95-150 with:
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
            d for d in all_docs if d.metadata.get("project") == project
        ]
    else:
        docs_to_export = all_docs

    # Create ZIP using shared utility
    zip_bytes = create_export_zip(docs_to_export, doc_store, ann_store, annotator)

    # Prepare response
    zip_buffer = io.BytesIO(zip_bytes)
    filename_safe = quote(project or "all-documents", safe="")
    filename = f"{filename_safe}.zip"

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

**Step 2: Run existing tests to verify refactor**

Run:
```bash
uv run pytest tests/test_export.py -v
```

Expected: PASS (all 5 tests)

**Step 3: Commit**

```bash
git add src/textractor/api/routers/documents.py
git commit -m "refactor: use shared export utility in API endpoint"
```

---

## Task 3: Create CLI Export Command

**Files:**
- Create: `src/textractor/cli/export.py`
- Test: `tests/test_cli_export.py`

**Step 1: Write failing test for CLI export**

Create `tests/test_cli_export.py`:

```python
"""Tests for CLI export command."""
import json
import tempfile
import zipfile
from pathlib import Path

import pytest

from textractor.cli.export import export_project
from textractor.api.storage import DocumentStore
from textractor.api.annotation_store import SQLiteAnnotationStore
from textractor.api.models import AnnotationFile, Span


@pytest.fixture
def test_project_setup():
    """Set up test project with documents and annotations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        doc_root = Path(tmpdir)
        db_path = doc_root / "test.db"

        # Create test documents
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

        # Initialize stores and add annotations
        doc_store = DocumentStore(doc_root)
        ann_store = SQLiteAnnotationStore(db_path)

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

        yield doc_root, db_path


def test_export_project_creates_zip_file(test_project_setup):
    """Test that export_project creates a valid ZIP file."""
    doc_root, db_path = test_project_setup
    output_path = doc_root / "export.zip"

    # Run export
    stats = export_project(
        project="test-project",
        output=output_path,
        doc_root=doc_root,
        db_path=db_path,
        annotator="default",
    )

    # Verify stats
    assert stats["documents"] == 2
    assert stats["annotations"] == 1
    assert stats["errors"] == 0

    # Verify ZIP file exists and has correct content
    assert output_path.exists()

    with zipfile.ZipFile(output_path, 'r') as zf:
        files = zf.namelist()
        assert "doc_001.json" in files
        assert "doc_002.json" in files
        assert "doc_001.ann.json" in files


def test_export_project_default_output_path(test_project_setup):
    """Test that export uses default output path when not specified."""
    doc_root, db_path = test_project_setup

    # Run export without specifying output
    stats = export_project(
        project="test-project",
        output=None,
        doc_root=doc_root,
        db_path=db_path,
    )

    # Should create file in current directory
    expected_path = Path.cwd() / "test-project.zip"
    assert expected_path.exists()

    # Clean up
    expected_path.unlink()


def test_export_nonexistent_project_returns_error(test_project_setup):
    """Test that exporting nonexistent project returns error stats."""
    doc_root, db_path = test_project_setup
    output_path = doc_root / "export.zip"

    # Run export for nonexistent project
    stats = export_project(
        project="nonexistent",
        output=output_path,
        doc_root=doc_root,
        db_path=db_path,
    )

    # Should have error
    assert stats["documents"] == 0
    assert stats["errors"] == 1
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_cli_export.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'textractor.cli.export'"

**Step 3: Write CLI implementation**

Create `src/textractor/cli/export.py`:

```python
"""CLI command for exporting projects."""
from __future__ import annotations

import logging
from pathlib import Path

from ..api.annotation_store import SQLiteAnnotationStore
from ..api.export_utils import create_export_zip
from ..api.storage import DocumentStore

logger = logging.getLogger(__name__)


def export_project(
    project: str,
    output: Path | None = None,
    doc_root: Path = Path("./data/documents"),
    db_path: Path = Path("./data/textractor.db"),
    annotator: str = "default",
) -> dict[str, int]:
    """
    Export a project's documents and annotations to a ZIP file.

    Args:
        project: Project name to export
        output: Output path for ZIP file (default: ./{project}.zip)
        doc_root: Document root directory
        db_path: SQLite database path
        annotator: Annotator name for annotations

    Returns:
        Dictionary with export statistics
    """
    stats = {
        "documents": 0,
        "annotations": 0,
        "errors": 0,
    }

    # Initialize stores
    try:
        doc_store = DocumentStore(doc_root)
        ann_store = SQLiteAnnotationStore(db_path)
    except Exception as e:
        logger.error(f"Failed to initialize stores: {e}")
        stats["errors"] += 1
        return stats

    # Get all documents and filter by project
    all_docs = doc_store.list_documents()
    docs_to_export = [
        d for d in all_docs if d.metadata.get("project") == project
    ]

    # Check if project exists
    if not docs_to_export:
        logger.error(f"No documents found for project '{project}'")
        stats["errors"] += 1
        return stats

    logger.info(f"Found {len(docs_to_export)} documents in project '{project}'")

    # Count annotations
    for doc_summary in docs_to_export:
        annotations = ann_store.get_annotations(doc_summary.id, annotator=annotator)
        if annotations:
            stats["annotations"] += 1

    stats["documents"] = len(docs_to_export)

    # Create ZIP
    try:
        zip_bytes = create_export_zip(docs_to_export, doc_store, ann_store, annotator)
    except Exception as e:
        logger.error(f"Failed to create ZIP: {e}")
        stats["errors"] += 1
        return stats

    # Determine output path
    if output is None:
        output = Path.cwd() / f"{project}.zip"

    # Write ZIP to file
    try:
        output.write_bytes(zip_bytes)
        logger.info(f"Exported to {output}")
    except Exception as e:
        logger.error(f"Failed to write ZIP file: {e}")
        stats["errors"] += 1
        return stats

    return stats


def print_export_report(stats: dict[str, int], output_path: Path) -> None:
    """Print a formatted export report."""
    print("\n=== Export Report ===")
    print(f"Documents:      {stats['documents']}")
    print(f"Annotations:    {stats['annotations']}")
    print(f"Output:         {output_path}")
    print("=" * 21)

    if stats["errors"] > 0:
        print("\n⚠️  Export failed. Check logs for details.")
    else:
        print(f"\n✓ Successfully exported to {output_path}!")


def main() -> None:
    """CLI entry point for export command."""
    import argparse
    import os

    parser = argparse.ArgumentParser(
        description="Export project documents and annotations to a ZIP file"
    )
    parser.add_argument(
        "project",
        type=str,
        help="Project name to export",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output path for ZIP file (default: ./{project}.zip)",
    )
    parser.add_argument(
        "--doc-root",
        type=Path,
        default=Path(os.environ.get("TEXTRACTOR_DOC_ROOT", "./data/documents")),
        help="Document root directory (default: $TEXTRACTOR_DOC_ROOT or ./data/documents)",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path(os.environ.get("TEXTRACTOR_DB_PATH", "./data/textractor.db")),
        help="SQLite database path (default: $TEXTRACTOR_DB_PATH or ./data/textractor.db)",
    )
    parser.add_argument(
        "--annotator",
        type=str,
        default="default",
        help="Annotator name for annotations (default: default)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # Determine output path
    output_path = args.output or Path.cwd() / f"{args.project}.zip"

    # Run export
    stats = export_project(
        project=args.project,
        output=output_path,
        doc_root=args.doc_root,
        db_path=args.db_path,
        annotator=args.annotator,
    )

    # Print report
    print_export_report(stats, output_path)

    # Exit with error code if there were any errors
    exit(1 if stats["errors"] > 0 else 0)


if __name__ == "__main__":
    main()
```

**Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_cli_export.py -v
```

Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add src/textractor/cli/export.py tests/test_cli_export.py
git commit -m "feat: add CLI export command"
```

---

## Task 4: Add CLI Routing

**Files:**
- Modify: `src/textractor/__init__.py:10-17`

**Step 1: Add export-project routing**

Modify `src/textractor/__init__.py`:

```python
def main() -> None:
    """Main CLI entry point - routes to server or subcommands."""
    # Check if a subcommand was provided
    if len(sys.argv) > 1:
        subcommand = sys.argv[1]

        if subcommand == "migrate-annotations":
            # Route to migration command
            from .cli.migrate import main as migrate_main
            sys.argv.pop(1)
            migrate_main()
            return

        elif subcommand == "export-project":
            # Route to export command
            from .cli.export import main as export_main
            sys.argv.pop(1)
            export_main()
            return

    # Default: run the server
    host = os.environ.get("TEXTRACTOR_HOST", "0.0.0.0")
    port = int(os.environ.get("TEXTRACTOR_PORT", "8000"))

    uvicorn.run(
        "textractor.api.main:app",
        host=host,
        port=port,
        reload=False,
    )
```

**Step 2: Test CLI routing manually**

Run:
```bash
uv run textractor export-project --help
```

Expected: Help text showing export-project usage

**Step 3: Commit**

```bash
git add src/textractor/__init__.py
git commit -m "feat: add CLI routing for export-project command"
```

---

## Task 5: Integration Test

**Files:**
- Test: Manual integration test

**Step 1: Create test project**

```bash
mkdir -p /tmp/test-export/documents
echo '{"id":"test_001","text":"Test doc","metadata":{"project":"my-project"}}' > /tmp/test-export/documents/test_001.json
```

**Step 2: Run export command**

```bash
TEXTRACTOR_DOC_ROOT=/tmp/test-export/documents \
TEXTRACTOR_DB_PATH=/tmp/test-export/test.db \
uv run textractor export-project my-project -o /tmp/test-export/output.zip --verbose
```

Expected: Success message with export report

**Step 3: Verify ZIP contents**

```bash
unzip -l /tmp/test-export/output.zip
```

Expected: Shows test_001.json in the ZIP

**Step 4: Clean up**

```bash
rm -rf /tmp/test-export
```

---

## Task 6: Update Documentation

**Files:**
- Modify: `CLAUDE.md` (add CLI command documentation)

**Step 1: Add CLI documentation**

Add to `CLAUDE.md` under the "Common Commands" section:

```markdown
### Project Export

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
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add CLI export command documentation"
```

---

## Task 7: Final Verification

**Files:**
- Test: Run full test suite

**Step 1: Run all tests**

```bash
uv run pytest -v
```

Expected: All tests pass

**Step 2: Run both CLI commands**

```bash
# Test help
uv run textractor export-project --help
uv run textractor migrate-annotations --help

# Test server still works
uv run textractor &
sleep 2
curl http://localhost:8000/api/documents
kill %1
```

Expected: All commands work correctly

**Step 3: Final commit if any fixes needed**

```bash
git add .
git commit -m "fix: final adjustments for CLI export"
```

---

## Summary

**Files Created:**
- `src/textractor/api/export_utils.py` - Shared ZIP creation logic
- `src/textractor/cli/export.py` - CLI export command
- `tests/test_export_utils.py` - Tests for export utility
- `tests/test_cli_export.py` - Tests for CLI command

**Files Modified:**
- `src/textractor/api/routers/documents.py` - Refactored to use shared logic
- `src/textractor/__init__.py` - Added CLI routing
- `CLAUDE.md` - Added documentation

**Test Coverage:**
- Unit tests for `create_export_zip()`
- Unit tests for `export_project()` function
- Integration test for CLI routing
- Existing API tests still pass

**Usage:**
```bash
uv run textractor export-project <project-name> [--output <path>] [--annotator <name>] [--verbose]
```
