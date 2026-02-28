# Health Endpoint Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `GET /health` endpoint that returns app status including SNOMED availability, doc root accessibility, document count, and DB connectivity.

**Architecture:** New `health.py` router registered in `main.py` alongside existing routers. All checks are lightweight inline calls using the existing dependency singletons. Always returns HTTP 200; `status` field is `"healthy"` or `"degraded"` depending on check results.

**Tech Stack:** FastAPI, Pydantic, pytest + TestClient (matches existing test pattern)

---

### Task 1: Create branch

**Files:**
- No code files

**Step 1: Create and switch to feature branch**

```bash
git checkout -b feature/74-health-endpoint
```

**Step 2: Verify**

```bash
git branch
```
Expected: `* feature/74-health-endpoint`

---

### Task 2: Write failing test for the health endpoint

**Files:**
- Create: `tests/test_health.py`

**Step 1: Write the failing tests**

Create `tests/test_health.py` with this exact content:

```python
"""Tests for the /health endpoint."""
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from textractor.api.dependencies import init_annotation_store, init_store, init_terminology
from textractor.api.main import create_app


@pytest.fixture
def client():
    """Test client with all dependencies initialized."""
    with tempfile.TemporaryDirectory() as tmpdir:
        doc_root = Path(tmpdir)
        init_store(doc_root)
        init_annotation_store(doc_root / "test.db")
        init_terminology(snomed_dir=None)
        app = create_app()
        yield TestClient(app)


@pytest.fixture
def client_with_docs():
    """Test client with pre-existing documents."""
    with tempfile.TemporaryDirectory() as tmpdir:
        doc_root = Path(tmpdir)

        # Write two document files
        (doc_root / "doc_001.json").write_text(
            '{"id": "doc_001", "text": "Patient has chest pain", "metadata": {}}'
        )
        (doc_root / "doc_002.json").write_text(
            '{"id": "doc_002", "text": "Follow-up visit", "metadata": {}}'
        )

        init_store(doc_root)
        init_annotation_store(doc_root / "test.db")
        init_terminology(snomed_dir=None)
        app = create_app()
        yield TestClient(app)


def test_health_returns_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_health_response_shape(client):
    resp = client.get("/health")
    body = resp.json()
    assert "status" in body
    assert "snomed_available" in body
    assert "doc_root_accessible" in body
    assert "document_count" in body
    assert "db_accessible" in body


def test_health_status_values(client):
    resp = client.get("/health")
    body = resp.json()
    assert body["status"] in ("healthy", "degraded")


def test_health_no_snomed(client):
    """Without SNOMED loaded, snomed_available should be False."""
    resp = client.get("/health")
    body = resp.json()
    assert body["snomed_available"] is False


def test_health_doc_root_accessible(client):
    resp = client.get("/health")
    body = resp.json()
    assert body["doc_root_accessible"] is True


def test_health_document_count_empty(client):
    resp = client.get("/health")
    body = resp.json()
    assert body["document_count"] == 0


def test_health_document_count_with_docs(client_with_docs):
    resp = client_with_docs.get("/health")
    body = resp.json()
    assert body["document_count"] == 2


def test_health_db_accessible(client):
    resp = client.get("/health")
    body = resp.json()
    assert body["db_accessible"] is True


def test_health_degraded_when_snomed_missing(client):
    """status is 'degraded' when snomed_available is False."""
    resp = client.get("/health")
    body = resp.json()
    # No SNOMED loaded → degraded
    assert body["status"] == "degraded"
```

**Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_health.py -v
```

Expected: All tests fail with `404 Not Found` or import errors (the endpoint doesn't exist yet).

**Step 3: Commit failing tests**

```bash
git add tests/test_health.py
git commit -m "test: add failing tests for GET /health endpoint (issue #74)"
```

---

### Task 3: Implement the health router

**Files:**
- Create: `src/textractor/api/routers/health.py`

**Step 1: Write the router**

Create `src/textractor/api/routers/health.py` with this exact content:

```python
"""Health check endpoint for infrastructure monitoring."""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Literal

from ..dependencies import _store, _terminology, _annotation_store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded"]
    snomed_available: bool
    doc_root_accessible: bool
    document_count: int
    db_accessible: bool


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """
    Return application health status.

    Always returns HTTP 200. Use the `status` field to distinguish
    healthy from degraded states. Intended for Docker HEALTHCHECK,
    load balancers, and monitoring systems.
    """
    snomed_available = _terminology is not None and _terminology.is_loaded

    doc_root_accessible = False
    document_count = 0
    if _store is not None:
        try:
            doc_root_accessible = os.access(_store.root, os.R_OK)
            document_count = len(_store.list_documents())
        except Exception:
            logger.exception("Health check: error accessing document store")

    db_accessible = False
    if _annotation_store is not None:
        try:
            import sqlite3
            with sqlite3.connect(_annotation_store.db_path, timeout=2.0) as conn:
                conn.execute("SELECT 1")
            db_accessible = True
        except Exception:
            logger.exception("Health check: error accessing SQLite database")

    all_ok = snomed_available and doc_root_accessible and db_accessible
    status: Literal["healthy", "degraded"] = "healthy" if all_ok else "degraded"

    return HealthResponse(
        status=status,
        snomed_available=snomed_available,
        doc_root_accessible=doc_root_accessible,
        document_count=document_count,
        db_accessible=db_accessible,
    )
```

**Step 2: Run tests — expect most to pass, but some may still fail**

```bash
uv run pytest tests/test_health.py -v
```

---

### Task 4: Wire the health router into main.py

**Files:**
- Modify: `src/textractor/api/main.py`

**Step 1: Add the import**

In `src/textractor/api/main.py`, find:

```python
from .routers import annotations, documents, preannotate
from .routers import terminology as terminology_router
```

Change to:

```python
from .routers import annotations, documents, preannotate
from .routers import terminology as terminology_router
from .routers import health as health_router
```

**Step 2: Register the router**

Find the block:

```python
    app.include_router(documents.router)
    app.include_router(annotations.router)
    app.include_router(preannotate.router)
    app.include_router(terminology_router.router)
```

Add after the last line:

```python
    app.include_router(health_router.router)
```

**Step 3: Run all health tests**

```bash
uv run pytest tests/test_health.py -v
```

Expected: All 9 tests PASS.

**Step 4: Run the full test suite to check for regressions**

```bash
uv run pytest --ignore=tests/test_snomed.py --ignore=tests/test_terminology_integration.py -v
```

Expected: All tests pass (the two ignored files require SNOMED CT data files).

**Step 5: Commit**

```bash
git add src/textractor/api/routers/health.py src/textractor/api/main.py
git commit -m "feat: add GET /health endpoint for infrastructure monitoring (issue #74)"
```

---

### Task 5: Open the PR

**Step 1: Push branch**

```bash
git push -u origin feature/74-health-endpoint
```

**Step 2: Create PR**

```bash
gh pr create \
  --title "feat: add GET /health endpoint (#74)" \
  --body "$(cat <<'EOF'
## Summary

- Adds `GET /health` endpoint (no `/api/` prefix — infrastructure convention)
- Returns 200 always with JSON body: `status`, `snomed_available`, `doc_root_accessible`, `document_count`, `db_accessible`
- `status` is `"healthy"` when all checks pass, `"degraded"` otherwise
- 9 new tests in `tests/test_health.py`

## Test plan

- [x] `GET /health` returns 200
- [x] Response shape matches spec
- [x] `snomed_available: false` when no SNOMED loaded
- [x] `doc_root_accessible: true` with valid tmpdir
- [x] `document_count` reflects actual files
- [x] `db_accessible: true` with valid SQLite DB
- [x] `status: "degraded"` when any check fails

Closes #74

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
