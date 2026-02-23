"""Migration tool for importing .ann.json files into SQLite."""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from ..api.annotation_store import SQLiteAnnotationStore
from ..api.models import AnnotationFile

logger = logging.getLogger(__name__)


def migrate_annotations(
    doc_root: Path,
    db_path: Path,
    annotator: str = "default",
    dry_run: bool = False,
    archive: bool = False,
) -> dict[str, int]:
    """
    Migrate .ann.json files to SQLite database.

    Args:
        doc_root: Root directory containing .ann.json files
        db_path: Path to SQLite database
        annotator: Annotator name for imported annotations (default: 'default')
        dry_run: If True, only report what would be done without making changes
        archive: If True, move original .ann.json files to .ann.json.bak after import

    Returns:
        Dictionary with migration statistics
    """
    stats = {
        "found": 0,
        "imported": 0,
        "skipped": 0,
        "errors": 0,
    }

    # Find all .ann.json files
    ann_files = list(doc_root.rglob("*.ann.json"))
    stats["found"] = len(ann_files)

    if stats["found"] == 0:
        logger.info("No .ann.json files found in %s", doc_root)
        return stats

    logger.info("Found %d .ann.json files", stats["found"])

    if dry_run:
        logger.info("DRY RUN: No changes will be made")
        for ann_file in ann_files:
            logger.info("Would import: %s", ann_file)
        return stats

    # Initialize annotation store
    annotation_store = SQLiteAnnotationStore(db_path)
    logger.info("Initialized annotation store at %s", db_path)

    # Import each annotation file
    for ann_file in ann_files:
        try:
            # Read and validate annotation file
            data = json.loads(ann_file.read_text(encoding="utf-8"))
            ann = AnnotationFile.model_validate(data)

            # Check if already imported
            if annotation_store.is_annotated(ann.doc_id, annotator=annotator):
                logger.warning(
                    "Annotations for %s (annotator=%s) already exist, skipping",
                    ann.doc_id,
                    annotator,
                )
                stats["skipped"] += 1
                continue

            # Import as version 1
            annotation_store.save_annotations(
                doc_id=ann.doc_id,
                annotations=ann,
                annotator=annotator,
                source="human",  # Legacy annotations treated as human-created
                model_name=None,
            )

            logger.info("Imported %s -> %s (annotator=%s)", ann_file, ann.doc_id, annotator)
            stats["imported"] += 1

            # Archive original file if requested
            if archive:
                backup_path = ann_file.with_suffix(".ann.json.bak")
                shutil.move(str(ann_file), str(backup_path))
                logger.info("Archived %s -> %s", ann_file, backup_path)

        except Exception as e:
            logger.error("Failed to import %s: %s", ann_file, e, exc_info=True)
            stats["errors"] += 1

    return stats


def print_migration_report(stats: dict[str, int]) -> None:
    """Print a formatted migration report."""
    print("\n=== Migration Report ===")
    print(f"Files found:    {stats['found']}")
    print(f"Imported:       {stats['imported']}")
    print(f"Skipped:        {stats['skipped']}")
    print(f"Errors:         {stats['errors']}")
    print("=" * 24)

    if stats["errors"] > 0:
        print("\n⚠️  Some files failed to import. Check logs for details.")
    elif stats["imported"] == 0 and stats["found"] > 0:
        print("\n⚠️  No files were imported (all skipped or errored).")
    elif stats["imported"] > 0:
        print(f"\n✓ Successfully imported {stats['imported']} annotation files!")


def main() -> None:
    """CLI entry point for migration command."""
    import argparse
    import os

    parser = argparse.ArgumentParser(
        description="Migrate .ann.json annotation files to SQLite database"
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
        help="Annotator name for imported annotations (default: default)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--archive",
        action="store_true",
        help="Archive original .ann.json files to .ann.json.bak after successful import",
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

    # Run migration
    stats = migrate_annotations(
        doc_root=args.doc_root,
        db_path=args.db_path,
        annotator=args.annotator,
        dry_run=args.dry_run,
        archive=args.archive,
    )

    # Print report
    print_migration_report(stats)

    # Exit with error code if there were any errors
    exit(1 if stats["errors"] > 0 else 0)


if __name__ == "__main__":
    main()
