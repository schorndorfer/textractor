import json
from textractor.api.models import Span, ReasoningStep, DocumentAnnotation, AnnotationFile


def test_span_backward_compatibility():
    """Test that spans without source field default to 'human'"""
    data = {"id": "span_abc123", "start": 0, "end": 5, "text": "hello"}
    span = Span.model_validate(data)
    assert span.source == "human"


def test_reasoning_step_backward_compatibility():
    """Test that reasoning steps without source field default to 'human'"""
    data = {
        "id": "step_abc123",
        "concept": {"code": "123", "display": "Test", "system": "SNOMED-CT"},
        "span_ids": [],
        "note": "",
    }
    step = ReasoningStep.model_validate(data)
    assert step.source == "human"


def test_document_annotation_backward_compatibility():
    """Test that document annotations without source field default to 'human'"""
    data = {
        "id": "ann_abc123",
        "concept": {"code": "123", "display": "Test", "system": "SNOMED-CT"},
        "evidence_span_ids": [],
        "reasoning_step_ids": [],
        "note": "",
    }
    ann = DocumentAnnotation.model_validate(data)
    assert ann.source == "human"


def test_annotation_file_with_mixed_sources():
    """Test that annotation files can contain mixed source annotations"""
    data = {
        "doc_id": "doc_001",
        "spans": [
            {"id": "span_1", "start": 0, "end": 5, "text": "hello", "source": "human"},
            {"id": "span_2", "start": 6, "end": 11, "text": "world", "source": "model"},
        ],
        "reasoning_steps": [],
        "document_annotations": [],
    }
    ann_file = AnnotationFile.model_validate(data)
    assert ann_file.spans[0].source == "human"
    assert ann_file.spans[1].source == "model"


def test_terminology_info_has_systems_field():
    from textractor.api.models import TerminologyInfo, TerminologySystemInfo
    info = TerminologyInfo(
        total_concepts=100,
        file_name="test",
        loaded=True,
        systems=[
            TerminologySystemInfo(system="SNOMED-CT", loaded=True, count=100),
            TerminologySystemInfo(system="ICD-10-CM", loaded=False, count=None),
        ]
    )
    assert len(info.systems) == 2
    assert info.systems[0].system == "SNOMED-CT"
    assert info.systems[1].loaded is False
