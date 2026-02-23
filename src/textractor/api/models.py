from __future__ import annotations

import uuid
from typing import Literal, Optional

from pydantic import BaseModel, Field


def _uuid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class Concept(BaseModel):
    code: str
    display: str
    system: str = "SNOMED-CT"


class Span(BaseModel):
    id: str = Field(default_factory=lambda: _uuid("span"))
    start: int
    end: int
    text: str
    source: Literal["human", "model"] = "human"


class ReasoningStep(BaseModel):
    id: str = Field(default_factory=lambda: _uuid("step"))
    concept: Concept
    span_ids: list[str] = Field(default_factory=list)
    note: str = ""
    source: Literal["human", "model"] = "human"


class DocumentAnnotation(BaseModel):
    id: str = Field(default_factory=lambda: _uuid("ann"))
    concept: Concept
    evidence_span_ids: list[str] = Field(default_factory=list)
    reasoning_step_ids: list[str] = Field(default_factory=list)
    note: str = ""
    source: Literal["human", "model"] = "human"
    category: Optional[str] = None  # Clinical category (e.g., "problem", "medication")


class AnnotationFile(BaseModel):
    doc_id: str
    spans: list[Span] = Field(default_factory=list)
    reasoning_steps: list[ReasoningStep] = Field(default_factory=list)
    document_annotations: list[DocumentAnnotation] = Field(default_factory=list)
    completed: bool = False


class Document(BaseModel):
    id: str
    text: str
    metadata: dict = Field(default_factory=dict)


class DocumentSummary(BaseModel):
    id: str
    metadata: dict
    is_annotated: bool
    is_completed: bool
    text_preview: str


class TerminologyConcept(BaseModel):
    code: str
    display: str
    system: str


class TerminologyInfo(BaseModel):
    total_concepts: int
    file_name: Optional[str]
    loaded: bool
