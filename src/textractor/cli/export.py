"""CLI tool for exporting projects as ZIP files."""

from __future__ import annotations

import logging
from pathlib import Path

from ..api.annotation_store import SQLiteAnnotationStore
from ..api.export_utils import create_export_zip
from ..api.storage import DocumentStore

logger = logging.getLogger(__name__)


def export_project(
    project: str,
    output_path: str | None,
    doc_store: DocumentStore,
    ann_store: SQLiteAnnotationStore,
    annotator: str = "default",
) -> dict[str, int | str]:
    """
    Export a project (or all documents) as a ZIP file.

    Args:
        project: Project name to export (or None for all documents)
        output_path: Output ZIP file path (default: {project}.zip in current directory)
        doc_store: Document store instance
        ann_store: Annotation store instance
        annotator: Annotator name for annotations (default: 'default')

    Returns:
        Dictionary with export statistics
    """
    stats = {
        "documents_exported": 0,
        "annotations_exported": 0,
        "errors": 0,
        "zip_path": "",
        "error_message": "",
    }

    # Determine output path
    if output_path is None:
        output_path = f"{project}.zip"

    # Convert to absolute path for stats
    output_path_obj = Path(output_path).resolve()
    stats["zip_path"] = str(output_path_obj)

    # Get documents to export
    all_docs = doc_store.list_documents()
    if project:
        docs_to_export = [d for d in all_docs if d.metadata.get("project") == project]
    else:
        docs_to_export = all_docs

    if not docs_to_export:
        error_msg = f"No documents found for project '{project}'"
        logger.error(error_msg)
        stats["errors"] = 1
        stats["error_message"] = error_msg
        return stats

    logger.info("Found %d documents to export", len(docs_to_export))

    try:
        # Create ZIP using shared utility
        zip_bytes = create_export_zip(
            docs_to_export=docs_to_export,
            doc_store=doc_store,
            ann_store=ann_store,
            annotator=annotator,
        )

        # Write ZIP to file
        output_path_obj.write_bytes(zip_bytes)

        # Count annotations
        for doc in docs_to_export:
            stats["documents_exported"] += 1
            if ann_store.get_annotations(doc.id, annotator=annotator):
                stats["annotations_exported"] += 1

        logger.info("Successfully exported to %s", output_path_obj)

    except Exception as e:
        logger.error("Failed to export project: %s", e, exc_info=True)
        stats["errors"] = 1
        stats["error_message"] = str(e)

    return stats


def print_export_report(stats: dict[str, int | str]) -> None:
    """Print a formatted export report."""
    print("\n=== Export Report ===")
    print(f"Documents:      {stats['documents_exported']}")
    print(f"Annotations:    {stats['annotations_exported']}")
    print(f"Errors:         {stats['errors']}")
    if stats["zip_path"]:
        print(f"Output:         {stats['zip_path']}")
    print("=" * 21)

    if stats["errors"] > 0:
        print("\n⚠️  Export failed. Check logs for details.")
        if stats["error_message"]:
            print(f"Error: {stats['error_message']}")
    elif stats["documents_exported"] == 0:
        print("\n⚠️  No documents were exported.")
    else:
        print(f"\n✓ Successfully exported {stats['documents_exported']} documents!")


def main() -> None:
    """CLI entry point for export command."""
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Export project as ZIP file")
    parser.add_argument(
        "project",
        type=str,
        help="Project name to export",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Output ZIP file path (default: {project}.zip)",
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

    # Initialize stores
    doc_store = DocumentStore(args.doc_root)
    ann_store = SQLiteAnnotationStore(args.db_path)
    logger.info("Initialized document store at %s", args.doc_root)
    logger.info("Initialized annotation store at %s", args.db_path)

    # Run export
    stats = export_project(
        project=args.project,
        output_path=args.output,
        doc_store=doc_store,
        ann_store=ann_store,
        annotator=args.annotator,
    )

    # Print report
    print_export_report(stats)

    # Exit with error code if there were any errors
    exit(1 if stats["errors"] > 0 else 0)


if __name__ == "__main__":
    main()
