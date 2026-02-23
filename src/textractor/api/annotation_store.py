"""SQLite-based annotation storage with version history and multi-user support."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Protocol

from .models import AnnotationFile


class AnnotationStore(Protocol):
    """Protocol defining the annotation storage interface."""

    def get_annotations(self, doc_id: str, annotator: str = "default") -> AnnotationFile | None:
        """Get the current annotations for a document and annotator."""
        ...

    def save_annotations(
        self,
        doc_id: str,
        annotations: AnnotationFile,
        annotator: str = "default",
        source: str = "human",
        model_name: str | None = None,
    ) -> int:
        """
        Save annotations as a new version (append-only).
        Returns the new version number.
        """
        ...

    def get_history(self, doc_id: str, annotator: str = "default") -> list[dict]:
        """Get version history for a document and annotator."""
        ...

    def revert_to_version(self, doc_id: str, version: int, annotator: str = "default") -> AnnotationFile:
        """Revert to a specific version by creating a new version with that content."""
        ...

    def delete_annotations(self, doc_id: str, annotator: str | None = None) -> None:
        """Delete all annotations for a document (and optionally a specific annotator)."""
        ...

    def is_annotated(self, doc_id: str, annotator: str = "default") -> bool:
        """Check if a document has any annotations."""
        ...

    def is_completed(self, doc_id: str, annotator: str = "default") -> bool:
        """Check if a document is marked as completed."""
        ...

    def set_completed(self, doc_id: str, completed: bool, annotator: str = "default") -> None:
        """Set the completed status for a document."""
        ...


class SQLiteAnnotationStore:
    """SQLite-based annotation storage with version history."""

    def __init__(self, db_path: str | Path):
        """Initialize the SQLite annotation store."""
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database schema and enable WAL mode."""
        conn = sqlite3.connect(self.db_path)
        try:
            # Enable WAL mode for concurrent access
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")

            # Create annotation_versions table (append-only)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS annotation_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_id TEXT NOT NULL,
                    annotator TEXT NOT NULL DEFAULT 'default',
                    version INTEGER NOT NULL,
                    annotations JSON NOT NULL,
                    source TEXT NOT NULL DEFAULT 'human',
                    model_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(doc_id, annotator, version)
                )
            """)

            # Create document_status table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS document_status (
                    doc_id TEXT NOT NULL,
                    annotator TEXT NOT NULL DEFAULT 'default',
                    completed BOOLEAN NOT NULL DEFAULT FALSE,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (doc_id, annotator)
                )
            """)

            # Create indexes for performance
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_annver_doc_annotator
                ON annotation_versions(doc_id, annotator)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_annver_created
                ON annotation_versions(created_at)
            """)

            # Create view for current annotations
            conn.execute("""
                CREATE VIEW IF NOT EXISTS current_annotations AS
                SELECT doc_id, annotator, annotations, source, model_name, created_at, version
                FROM annotation_versions v1
                WHERE version = (
                    SELECT MAX(version)
                    FROM annotation_versions v2
                    WHERE v2.doc_id = v1.doc_id AND v2.annotator = v1.annotator
                )
            """)

            conn.commit()
        finally:
            conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_annotations(self, doc_id: str, annotator: str = "default") -> AnnotationFile | None:
        """Get the current annotations for a document and annotator."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT annotations FROM current_annotations WHERE doc_id = ? AND annotator = ?",
                (doc_id, annotator),
            )
            row = cursor.fetchone()
            if not row:
                return None

            # Parse JSON and reconstruct AnnotationFile
            data = json.loads(row["annotations"])

            # Get completed status
            cursor = conn.execute(
                "SELECT completed FROM document_status WHERE doc_id = ? AND annotator = ?",
                (doc_id, annotator),
            )
            status_row = cursor.fetchone()
            completed = bool(status_row["completed"]) if status_row else False

            return AnnotationFile(
                doc_id=doc_id,
                spans=data.get("spans", []),
                reasoning_steps=data.get("reasoning_steps", []),
                document_annotations=data.get("document_annotations", []),
                completed=completed,
            )
        finally:
            conn.close()

    def save_annotations(
        self,
        doc_id: str,
        annotations: AnnotationFile,
        annotator: str = "default",
        source: str = "human",
        model_name: str | None = None,
    ) -> int:
        """
        Save annotations as a new version (append-only).
        Returns the new version number.
        """
        conn = self._get_connection()
        try:
            # Get next version number
            cursor = conn.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 as next_version FROM annotation_versions WHERE doc_id = ? AND annotator = ?",
                (doc_id, annotator),
            )
            next_version = cursor.fetchone()["next_version"]

            # Prepare JSON payload (without doc_id and completed)
            payload = {
                "spans": [span.model_dump() for span in annotations.spans],
                "reasoning_steps": [step.model_dump() for step in annotations.reasoning_steps],
                "document_annotations": [ann.model_dump() for ann in annotations.document_annotations],
            }

            # Insert new version
            conn.execute(
                """
                INSERT INTO annotation_versions (doc_id, annotator, version, annotations, source, model_name, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (doc_id, annotator, next_version, json.dumps(payload), source, model_name, datetime.utcnow()),
            )

            # Update completed status
            conn.execute(
                """
                INSERT INTO document_status (doc_id, annotator, completed, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(doc_id, annotator) DO UPDATE SET
                    completed = excluded.completed,
                    updated_at = excluded.updated_at
                """,
                (doc_id, annotator, annotations.completed, datetime.utcnow()),
            )

            conn.commit()
            return next_version
        finally:
            conn.close()

    def get_history(self, doc_id: str, annotator: str = "default") -> list[dict]:
        """Get version history for a document and annotator."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """
                SELECT version, source, model_name, created_at
                FROM annotation_versions
                WHERE doc_id = ? AND annotator = ?
                ORDER BY version DESC
                """,
                (doc_id, annotator),
            )
            rows = cursor.fetchall()
            return [
                {
                    "version": row["version"],
                    "source": row["source"],
                    "model_name": row["model_name"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ]
        finally:
            conn.close()

    def revert_to_version(self, doc_id: str, version: int, annotator: str = "default") -> AnnotationFile:
        """Revert to a specific version by creating a new version with that content."""
        conn = self._get_connection()
        try:
            # Get the target version
            cursor = conn.execute(
                "SELECT annotations FROM annotation_versions WHERE doc_id = ? AND annotator = ? AND version = ?",
                (doc_id, annotator, version),
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Version {version} not found for doc_id={doc_id}, annotator={annotator}")

            # Parse annotations
            data = json.loads(row["annotations"])

            # Get current completed status
            cursor = conn.execute(
                "SELECT completed FROM document_status WHERE doc_id = ? AND annotator = ?",
                (doc_id, annotator),
            )
            status_row = cursor.fetchone()
            completed = bool(status_row["completed"]) if status_row else False

            # Create AnnotationFile
            annotation_file = AnnotationFile(
                doc_id=doc_id,
                spans=data.get("spans", []),
                reasoning_steps=data.get("reasoning_steps", []),
                document_annotations=data.get("document_annotations", []),
                completed=completed,
            )

            # Save as new version
            self.save_annotations(
                doc_id=doc_id,
                annotations=annotation_file,
                annotator=annotator,
                source="human",  # Reverts are human actions
                model_name=None,
            )

            return annotation_file
        finally:
            conn.close()

    def delete_annotations(self, doc_id: str, annotator: str | None = None) -> None:
        """Delete all annotations for a document (and optionally a specific annotator)."""
        conn = self._get_connection()
        try:
            if annotator:
                # Delete specific annotator's data
                conn.execute("DELETE FROM annotation_versions WHERE doc_id = ? AND annotator = ?", (doc_id, annotator))
                conn.execute("DELETE FROM document_status WHERE doc_id = ? AND annotator = ?", (doc_id, annotator))
            else:
                # Delete all annotators' data for this document
                conn.execute("DELETE FROM annotation_versions WHERE doc_id = ?", (doc_id,))
                conn.execute("DELETE FROM document_status WHERE doc_id = ?", (doc_id,))

            conn.commit()
        finally:
            conn.close()

    def is_annotated(self, doc_id: str, annotator: str = "default") -> bool:
        """Check if a document has any annotations."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT 1 FROM annotation_versions WHERE doc_id = ? AND annotator = ? LIMIT 1",
                (doc_id, annotator),
            )
            return cursor.fetchone() is not None
        finally:
            conn.close()

    def is_completed(self, doc_id: str, annotator: str = "default") -> bool:
        """Check if a document is marked as completed."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT completed FROM document_status WHERE doc_id = ? AND annotator = ?",
                (doc_id, annotator),
            )
            row = cursor.fetchone()
            return bool(row["completed"]) if row else False
        finally:
            conn.close()

    def set_completed(self, doc_id: str, completed: bool, annotator: str = "default") -> None:
        """Set the completed status for a document."""
        conn = self._get_connection()
        try:
            conn.execute(
                """
                INSERT INTO document_status (doc_id, annotator, completed, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(doc_id, annotator) DO UPDATE SET
                    completed = excluded.completed,
                    updated_at = excluded.updated_at
                """,
                (doc_id, annotator, completed, datetime.utcnow()),
            )
            conn.commit()
        finally:
            conn.close()
