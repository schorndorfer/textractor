"""ICD-10-CM search using SQLite FTS5 full-text search."""
import csv
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ICD10CMSearch:
    """
    ICD-10-CM search using SQLite FTS5 for persistent storage and efficient searching.

    Features:
    - Persistent storage (no reload on restart)
    - Fast full-text search with FTS5 trigram tokenization
    - Custom relevance scoring (exact, prefix, word boundary, position-based)
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()

    def _get_connection(self) -> sqlite3.Connection:
        if self.conn is None:
            if self.db_path:
                self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            else:
                self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        return self.conn

    def build_index(self, file_path: Path) -> int:
        """
        Build SQLite FTS5 index from CMS ICD-10-CM flat file.

        Args:
            file_path: Path to tab-delimited file (no header): code TAB description

        Returns:
            Number of codes indexed
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS icd10cm_fts USING fts5(
                code,
                description,
                tokenize='trigram'
            )
        """)
        cursor.execute("DELETE FROM icd10cm_fts")

        try:
            count = 0
            batch = []
            with open(file_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f, delimiter="\t")
                for row in reader:
                    if len(row) < 2:
                        continue
                    code, description = row[0].strip(), row[1].strip()
                    if code and description:
                        batch.append((code, description))
                        count += 1
                        if len(batch) >= 10000:
                            cursor.executemany(
                                "INSERT INTO icd10cm_fts (code, description) VALUES (?, ?)",
                                batch,
                            )
                            batch = []

            if batch:
                cursor.executemany(
                    "INSERT INTO icd10cm_fts (code, description) VALUES (?, ?)",
                    batch,
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        logger.info("Indexed %d ICD-10-CM codes in SQLite", count)
        return count

    def is_indexed(self) -> bool:
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM icd10cm_fts")
                return cursor.fetchone()[0] > 0
            except sqlite3.OperationalError:
                return False

    def _score_match(self, query: str, description: str, base_score: float) -> float:
        """Multi-factor scoring — identical logic to SNOMEDSearch._score_match."""
        query_lower = query.lower()
        desc_lower = description.lower()

        if query_lower == desc_lower:
            return base_score + 100
        if desc_lower.startswith(query_lower):
            return base_score + 80

        words = desc_lower.split()
        for i, word in enumerate(words):
            if word.startswith(query_lower):
                return base_score + max(60 - (i * 5), 30)

        if query_lower in desc_lower:
            position = desc_lower.index(query_lower)
            position_ratio = position / max(len(desc_lower), 1)
            return base_score + (40 - position_ratio * 20)

        return base_score

    def search(self, query: str, limit: int = 20) -> list[dict]:
        """
        Search ICD-10-CM descriptions using FTS5 full-text search.

        Returns list of dicts with keys: code, description, score
        """
        if not query.strip():
            return []

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            escaped = query.strip().replace('"', '""')
            fts_query = f'"{escaped}"'

            cursor.execute("""
                SELECT code, description, rank
                FROM icd10cm_fts
                WHERE icd10cm_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (fts_query, limit * 3))

            results = cursor.fetchall()

            scored = []
            for code, description, fts_rank in results:
                base_score = abs(fts_rank)
                custom_score = self._score_match(query, description, base_score)
                scored.append({
                    "code": code,
                    "description": description,
                    "score": round(custom_score, 1),
                })

            scored.sort(key=lambda x: x["score"], reverse=True)

            seen_codes: set[str] = set()
            unique_results = []
            for result in scored:
                if result["code"] not in seen_codes:
                    seen_codes.add(result["code"])
                    unique_results.append(result)
            return unique_results[:limit]

    def close(self):
        with self._lock:
            if self.conn:
                self.conn.close()
                self.conn = None

    def __del__(self):
        self.close()
