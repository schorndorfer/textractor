"""SQLite-based SNOMED CT search with FTS5 full-text search."""
import csv
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class SNOMEDSearchSQLite:
    """
    SNOMED CT search using SQLite FTS5 for persistent storage and efficient searching.

    Benefits over in-memory approach:
    - Persistent storage (no reload on restart)
    - Lower memory footprint
    - Fast full-text search with FTS5
    - Supports substring matching with trigram tokenization
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize SQLite SNOMED search.

        Args:
            db_path: Path to SQLite database file. If None, uses in-memory database.
        """
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()  # Ensure thread-safe access

    def _get_connection(self) -> sqlite3.Connection:
        """
        Get or create database connection.

        Uses check_same_thread=False to allow cross-thread access.
        This is safe for our use case since we only do read operations
        after initial database build.
        """
        if self.conn is None:
            if self.db_path:
                self.conn = sqlite3.connect(
                    str(self.db_path),
                    check_same_thread=False
                )
            else:
                self.conn = sqlite3.connect(
                    ":memory:",
                    check_same_thread=False
                )
        return self.conn

    def build_index(self, rf2_dir: Path) -> int:
        """
        Build SQLite FTS5 index from SNOMED RF2 files.

        Args:
            rf2_dir: Path to directory containing SNOMED RF2 files

        Returns:
            Number of descriptions indexed
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Create FTS5 virtual table with trigram tokenizer for substring matching
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS snomed_fts USING fts5(
                concept_id,
                term,
                term_type,
                tokenize='trigram'
            )
        """)

        # Clear existing data
        cursor.execute("DELETE FROM snomed_fts")

        # Find description files
        desc_files = list(rf2_dir.glob("**/sct2_Description_Full-en*.txt"))
        if not desc_files:
            desc_files = list(rf2_dir.glob("**/sct2_Description_Snapshot-en*.txt"))

        if not desc_files:
            raise FileNotFoundError(f"No SNOMED description files found in {rf2_dir}")

        count = 0
        for desc_file in desc_files:
            with open(desc_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter="\t")
                batch = []

                for row in reader:
                    if row["active"] == "1":
                        term_type = "FSN" if row["typeId"] == "900000000000003001" else "SYNONYM"
                        batch.append((
                            int(row["conceptId"]),
                            row["term"],
                            term_type
                        ))
                        count += 1

                        # Insert in batches for performance
                        if len(batch) >= 10000:
                            cursor.executemany(
                                "INSERT INTO snomed_fts (concept_id, term, term_type) VALUES (?, ?, ?)",
                                batch
                            )
                            batch = []

                # Insert remaining
                if batch:
                    cursor.executemany(
                        "INSERT INTO snomed_fts (concept_id, term, term_type) VALUES (?, ?, ?)",
                        batch
                    )

        conn.commit()
        logger.info("Indexed %d active SNOMED descriptions in SQLite", count)
        return count

    def is_indexed(self) -> bool:
        """Check if the database has been indexed."""
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM snomed_fts")
                count = cursor.fetchone()[0]
                return count > 0
            except sqlite3.OperationalError:
                return False

    def _score_match(self, query: str, term: str, base_score: float) -> float:
        """
        Multi-factor scoring for better relevance ranking.

        Priority order:
        1. Exact match (100 bonus)
        2. Prefix match (80 bonus)
        3. Word boundary match (60 bonus)
        4. Contains match with position bonus (40-20 bonus)
        5. FTS5 rank (base score)
        """
        query_lower = query.lower()
        term_lower = term.lower()

        # Exact match
        if query_lower == term_lower:
            return base_score + 100

        # Prefix match (term starts with query)
        if term_lower.startswith(query_lower):
            return base_score + 80

        # Word boundary match (query matches start of a word in term)
        words = term_lower.split()
        for i, word in enumerate(words):
            if word.startswith(query_lower):
                # Earlier words get higher bonus
                position_bonus = 60 - (i * 5)
                return base_score + max(position_bonus, 30)

        # Contains match with position-based bonus
        if query_lower in term_lower:
            position = term_lower.index(query_lower)
            # Earlier positions get higher bonus (40 at start, 20 at end)
            position_ratio = position / max(len(term_lower), 1)
            position_bonus = 40 - (position_ratio * 20)
            return base_score + position_bonus

        # Just base score
        return base_score

    def search(self, query: str, limit: int = 20) -> list[dict]:
        """
        Search SNOMED descriptions using FTS5 full-text search.

        Args:
            query: Search query string
            limit: Maximum number of results to return

        Returns:
            List of matching descriptions with scores
        """
        if not query.strip():
            return []

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            # FTS5 MATCH query - rank is negative (higher is better match)
            # We get more results than needed for re-ranking
            cursor.execute("""
                SELECT concept_id, term, term_type, rank
                FROM snomed_fts
                WHERE snomed_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (query, limit * 3))

            results = cursor.fetchall()

            # Re-rank with custom scoring
            scored_results = []
            for concept_id, term, term_type, fts_rank in results:
                # Convert FTS5 rank (negative) to positive score
                # FTS rank is typically between -1 and -30
                base_score = abs(fts_rank)
                custom_score = self._score_match(query, term, base_score)

                scored_results.append({
                    "concept_id": concept_id,
                    "term": term,
                    "type": term_type,
                    "score": round(custom_score, 1)
                })

            # Sort by custom score (descending)
            scored_results.sort(key=lambda x: x["score"], reverse=True)

            # Deduplicate by concept_id, keeping highest scoring match for each
            seen_concepts = set()
            unique_results = []
            for result in scored_results:
                if result["concept_id"] not in seen_concepts:
                    seen_concepts.add(result["concept_id"])
                    unique_results.append(result)

            # Return top unique results
            return unique_results[:limit]

    def close(self):
        """Close database connection."""
        with self._lock:
            if self.conn:
                self.conn.close()
                self.conn = None

    def __del__(self):
        """Cleanup on deletion."""
        self.close()
