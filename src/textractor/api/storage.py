from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from .models import Document, DocumentSummary

logger = logging.getLogger(__name__)


class DocumentStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def list_documents(self) -> list[DocumentSummary]:
        """
        List all documents (annotation status populated by caller from SQLite).

        Note: is_annotated and is_completed are set to False here. The caller
        (documents router) should update these fields by querying the annotation store.
        """
        summaries: list[DocumentSummary] = []
        for path in sorted(self.root.rglob("*.json")):
            if path.name.endswith(".ann.json"):
                continue
            try:
                doc = self._read_document(path)
                summaries.append(
                    DocumentSummary(
                        id=doc.id,
                        metadata=doc.metadata,
                        is_annotated=False,  # Populated by caller from SQLite
                        is_completed=False,  # Populated by caller from SQLite
                        text_preview=doc.text[:200],
                    )
                )
            except Exception:
                logger.warning("Could not read %s, skipping", path)
        return summaries

    def get_document(self, doc_id: str) -> Optional[Document]:
        path = self._doc_path(doc_id)
        if not path.exists():
            return None
        return self._read_document(path)

    def save_document(self, doc: Document) -> None:
        path = self._doc_path(doc.id)
        path.write_text(doc.model_dump_json(indent=2), encoding="utf-8")

    def document_exists(self, doc_id: str) -> bool:
        return self._doc_path(doc_id).exists()

    def _doc_path(self, doc_id: str) -> Path:
        return self.root / f"{doc_id}.json"

    def _ann_path(self, doc_id: str) -> Path:
        return self.root / f"{doc_id}.ann.json"

    @staticmethod
    def _read_document(path: Path) -> Document:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Document.model_validate(data)
