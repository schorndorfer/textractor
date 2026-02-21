from __future__ import annotations

import csv
import io
import logging
from pathlib import Path
from typing import Optional

from .models import TerminologyConcept, TerminologyInfo

logger = logging.getLogger(__name__)


class TerminologyIndex:
    def __init__(self) -> None:
        self._concepts: list[TerminologyConcept] = []
        self._file_name: Optional[str] = None

    @property
    def is_loaded(self) -> bool:
        return len(self._concepts) > 0

    def info(self) -> TerminologyInfo:
        return TerminologyInfo(
            total_concepts=len(self._concepts),
            file_name=self._file_name,
            loaded=self.is_loaded,
        )

    def load_from_path(self, path: Path) -> int:
        content = path.read_text(encoding="utf-8")
        count = self._parse_tsv(content)
        self._file_name = path.name
        return count

    def load_from_bytes(self, data: bytes, filename: str) -> int:
        content = data.decode("utf-8")
        count = self._parse_tsv(content)
        self._file_name = filename
        return count

    def search(self, query: str, limit: int = 20) -> list[TerminologyConcept]:
        if not query:
            return []
        q = query.lower()
        results = [c for c in self._concepts if q in c.display.lower()]
        return results[:limit]

    def _parse_tsv(self, content: str) -> int:
        concepts: list[TerminologyConcept] = []
        reader = csv.DictReader(io.StringIO(content), delimiter="\t")

        required = {"code", "display", "system"}
        fieldnames = set(reader.fieldnames or [])
        if not required.issubset(fieldnames):
            raise ValueError(
                f"TSV must have header columns: code, display, system. Got: {list(fieldnames)}"
            )

        for row in reader:
            code = (row.get("code") or "").strip()
            display = (row.get("display") or "").strip()
            system = (row.get("system") or "SNOMED-CT").strip()
            if not code or not display:
                continue
            concepts.append(TerminologyConcept(code=code, display=display, system=system))

        self._concepts = concepts
        logger.info("Loaded %d concepts", len(concepts))
        return len(concepts)
