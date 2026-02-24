# CLI Export Command Design

**Date:** 2026-02-23
**Status:** Approved

## Overview

Add a CLI command to export project documents and annotations as ZIP files, matching the functionality of the GUI export button. The CLI should work standalone without requiring the server to be running.

## Requirements

- Export a named project's documents and annotations to a ZIP file
- Support custom output paths with sensible defaults
- Support custom annotator names (default: "default")
- Work independently of the running API server
- Reuse existing export logic to avoid code duplication

## Architecture

### Implementation Approach

Extract shared export logic from the API endpoint into a reusable utility, then create a CLI command that uses this shared logic. This follows the DRY principle and ensures consistency between API and CLI export behavior.

### Component Structure

1. **`src/textractor/api/export_utils.py`** (new)
   - Shared export logic extracted from API endpoint
   - Used by both API and CLI

2. **`src/textractor/cli/export.py`** (new)
   - CLI command implementation
   - Follows pattern established by `migrate.py`

3. **`src/textractor/__init__.py`** (modified)
   - Add routing for `export-project` subcommand

4. **`src/textractor/api/routers/documents.py`** (modified)
   - Refactor to use shared export logic from `export_utils.py`

## CLI Interface

### Command

```bash
textractor export-project <project-name> [options]
```

### Arguments

- `project` (positional, required) - The project name to export

### Flags

- `--output` / `-o` (optional) - Output path for ZIP file
  Default: `./{project-name}.zip` in current directory

- `--annotator` (optional) - Annotator name for annotations
  Default: `"default"`

- `--doc-root` (optional) - Document root directory
  Default: `$TEXTRACTOR_DOC_ROOT` or `./data/documents`

- `--db-path` (optional) - SQLite database path
  Default: `$TEXTRACTOR_DB_PATH` or `./data/textractor.db`

- `--verbose` / `-v` (optional) - Enable verbose logging

### Usage Examples

```bash
# Export "my-project" to ./my-project.zip
textractor export-project my-project

# Export to specific location
textractor export-project my-project --output /path/to/backup.zip

# Export with custom annotator
textractor export-project my-project --annotator john_doe

# Verbose output
textractor export-project my-project --verbose
```

### Output

**Success:**
- Summary report showing:
  - Number of documents exported
  - Number of annotations exported
  - Output file path
- Exit code: 0

**Error:**
- Clear error messages to stderr
- Exit code: 1

## Implementation Details

### `export_utils.py` - Shared Export Logic

```python
def create_export_zip(
    docs_to_export: list[DocumentSummary],
    doc_store: DocumentStore,
    ann_store: SQLiteAnnotationStore,
    annotator: str = "default"
) -> bytes:
    """Create ZIP containing documents and annotations.

    Args:
        docs_to_export: List of document summaries to export
        doc_store: Document store instance
        ann_store: Annotation store instance
        annotator: Annotator name for annotations

    Returns:
        ZIP file as bytes
    """
```

**Responsibilities:**
- Create in-memory ZIP file with documents and annotations
- Handle missing documents/annotations gracefully (log warnings)
- Return bytes for caller to stream (API) or write (CLI)

### `export.py` - CLI Implementation

**Main function structure:**

1. Parse CLI arguments with argparse
2. Initialize `DocumentStore` and `SQLiteAnnotationStore` directly
3. List all documents and filter by project name
4. Validate project exists and has documents
5. Call `create_export_zip()` to generate ZIP bytes
6. Write bytes to output file
7. Print summary report
8. Return appropriate exit code

**Pattern follows `migrate.py`:**
- Uses argparse for argument parsing
- Uses logging module for output (INFO default, DEBUG with `-v`)
- Returns statistics dict for testing
- Prints formatted report
- Exit codes: 0 success, 1 failure

### `documents.py` - Refactored API Endpoint

**Simplified `export_project()` endpoint:**

1. Get all documents from store
2. Filter by project if specified
3. Call `create_export_zip()` with filtered documents
4. Return `StreamingResponse` with ZIP bytes

## Error Handling

### Project Validation

- **No matching documents:** Error message "No documents found for project '{name}'" + exit code 1
- **Empty project (no annotations):** Warning logged, ZIP created with just documents

### File System Errors

- **Output path not writable:** Error "Cannot write to {path}: {error}" + exit code 1
- **Output file exists:** Overwrite without prompting (standard CLI behavior)
- **Doc root / DB path missing:** Error with clear instructions + exit code 1

### Database Errors

- **SQLite connection failure:** Error with suggestion to check `--db-path` + exit code 1
- **Missing annotations:** Log warning, continue exporting (same as API)

### Partial Failures

- **Some documents fail to load:** Log warnings, continue, show failures in summary
- **All documents fail:** Error exit code 1

### Logging Strategy

- **Default (INFO):** Progress messages (e.g., "Exporting 5 documents...")
- **Verbose (-v):** Debug details (each file added to ZIP)
- **Errors:** Always to stderr regardless of verbosity

## Testing Considerations

- Unit tests for `create_export_zip()` with mock stores
- CLI integration tests with temporary directories
- Test error cases: missing project, permission errors, DB errors
- Test default output path generation
- Test custom output paths (relative and absolute)

## Documentation Updates

- Update `CLAUDE.md` with new CLI command
- Update README if it documents CLI commands
- Add usage examples to help text
