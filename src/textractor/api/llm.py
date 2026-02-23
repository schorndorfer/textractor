from __future__ import annotations

import logging
from typing import Any

import anthropic
from rapidfuzz import fuzz

from .models import AnnotationFile, Concept, DocumentAnnotation, ReasoningStep, Span, TerminologyConcept

logger = logging.getLogger(__name__)

# Clinical categories to keep when filtering annotations
CLINICAL_CATEGORIES = {
    "problem",
    "procedure",
    "medication",
    "lab",
    "symptom",
    "diagnosis",
    "finding",
    "sign",
    "device",
    "allergy",
}


def extract_medical_terms(text: str, api_key: str, model: str = "claude-sonnet-4-5") -> list[str]:
    """
    Extract medical terms from clinical text using Claude AI.

    Args:
        text: Clinical document text
        api_key: Anthropic API key
        model: Model name to use

    Returns:
        List of extracted medical terms

    Raises:
        ValueError: If LLM response is invalid
        anthropic.APIError: If API call fails
    """
    client = anthropic.Anthropic(api_key=api_key)

    tools = [
        {
            "name": "extract_medical_terms",
            "description": "Extract medical terms and concepts from clinical text",
            "input_schema": {
                "type": "object",
                "properties": {
                    "terms": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of medical terms, conditions, symptoms, or diagnoses",
                    }
                },
                "required": ["terms"],
            },
        }
    ]

    prompt = f"""Analyze this clinical document and extract all medical terms, conditions, symptoms, procedures, and diagnoses mentioned.

Clinical Text:
{text}

Return a list of medical terms that should be coded using clinical terminology (SNOMED-CT). Include:
- Diagnoses and conditions
- Symptoms and findings
- Procedures
- Medications (if present)
- Anatomical locations (if clinically relevant)

Be thorough but only include medically significant terms."""

    response = client.messages.create(
        model=model,
        max_tokens=1024,
        temperature=0.0,
        tools=tools,
        messages=[{"role": "user", "content": prompt}],
    )

    logger.info(f"Term extraction: stop_reason={response.stop_reason}, usage={response.usage}")

    if response.stop_reason != "tool_use":
        raise ValueError("LLM did not return structured output")

    tool_calls = [block for block in response.content if block.type == "tool_use"]
    if not tool_calls:
        raise ValueError("No tool calls found in LLM response")

    tool_input = tool_calls[0].input
    terms = tool_input.get("terms", [])

    logger.info(f"Extracted {len(terms)} medical terms")
    return terms


def generate_annotations_raw(
    text: str,
    snomed_candidates: list[TerminologyConcept],
    api_key: str,
    model: str = "claude-sonnet-4-5",
) -> dict[str, Any]:
    """
    Generate structured annotations using Claude AI with SNOMED context.

    Args:
        text: Clinical document text
        snomed_candidates: SNOMED concepts from terminology search
        api_key: Anthropic API key
        model: Model name to use

    Returns:
        Raw annotation data with indices (not IDs):
        {
            "spans": [{"start": int, "end": int, "text": str}, ...],
            "reasoning_steps": [{
                "concept_code": str,
                "concept_display": str,
                "span_indices": [int, ...],
                "note": str
            }, ...],
            "document_annotations": [{
                "concept_code": str,
                "concept_display": str,
                "evidence_span_indices": [int, ...],
                "reasoning_step_indices": [int, ...],
                "note": str
            }, ...]
        }

    Raises:
        ValueError: If LLM response is invalid
        anthropic.APIError: If API call fails
    """
    client = anthropic.Anthropic(api_key=api_key)

    # Format SNOMED candidates for prompt
    snomed_list = "\n".join(
        f"- {c.code}: {c.display}" for c in snomed_candidates
    )

    tools = [
        {
            "name": "annotate_document",
            "description": "Generate structured annotations for clinical text",
            "input_schema": {
                "type": "object",
                "properties": {
                    "spans": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "start": {"type": "integer"},
                                "end": {"type": "integer"},
                                "text": {"type": "string"},
                            },
                            "required": ["start", "end", "text"],
                        },
                    },
                    "reasoning_steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "concept_code": {"type": "string"},
                                "concept_display": {"type": "string"},
                                "span_indices": {"type": "array", "items": {"type": "integer"}},
                                "note": {"type": "string"},
                            },
                            "required": ["concept_code", "concept_display", "span_indices"],
                        },
                    },
                    "document_annotations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "concept_code": {"type": "string"},
                                "concept_display": {"type": "string"},
                                "evidence_span_indices": {"type": "array", "items": {"type": "integer"}},
                                "reasoning_step_indices": {"type": "array", "items": {"type": "integer"}},
                                "note": {"type": "string"},
                            },
                            "required": ["concept_code", "concept_display"],
                        },
                    },
                },
                "required": ["spans", "reasoning_steps", "document_annotations"],
            },
        }
    ]

    prompt = f"""Annotate this clinical document with structured information.

Clinical Text:
{text}

Available SNOMED-CT Concepts:
{snomed_list}

Instructions:
1. Identify text spans that provide evidence for clinical findings
2. Create reasoning steps linking spans to SNOMED concepts
3. Create document-level annotations for the primary diagnoses/findings
4. ONLY use SNOMED codes from the provided list above
5. Use span_indices and reasoning_step_indices to reference items by array position (0-indexed)
6. Be accurate - only annotate what is clearly stated in the text

Return structured annotations following the tool schema."""

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        temperature=0.0,
        tools=tools,
        messages=[{"role": "user", "content": prompt}],
    )

    logger.info(f"Annotation generation: stop_reason={response.stop_reason}, usage={response.usage}")

    if response.stop_reason != "tool_use":
        raise ValueError("LLM did not return structured output")

    tool_calls = [block for block in response.content if block.type == "tool_use"]
    if not tool_calls:
        raise ValueError("No tool calls found in LLM response")

    annotations = tool_calls[0].input

    logger.info(
        f"Generated {len(annotations.get('spans', []))} spans, "
        f"{len(annotations.get('reasoning_steps', []))} steps, "
        f"{len(annotations.get('document_annotations', []))} annotations"
    )

    return annotations


def validate_span(span: dict[str, Any], doc_text: str) -> bool:
    """
    Check if span offsets are correct.

    Args:
        span: Span dict with 'start', 'end', 'text'
        doc_text: Full document text

    Returns:
        True if offsets are correct, False otherwise
    """
    try:
        actual_text = doc_text[span["start"]: span["end"]]
        return actual_text == span["text"]
    except IndexError:
        return False


def recover_span_offsets(
    span: dict[str, Any],
    doc_text: str,
    threshold: int = 90,
) -> tuple[int, int] | None:
    """
    Attempt to find correct offsets for a misaligned span using fuzzy matching.

    Args:
        span: Span dict with 'text'
        doc_text: Full document text
        threshold: Minimum similarity score (0-100)

    Returns:
        (new_start, new_end) tuple if found, None otherwise
    """
    span_text = span["text"]
    span_length = len(span_text)

    if span_length == 0 or span_length > len(doc_text):
        return None

    best_score = 0
    best_offset = None

    # Sliding window search
    for i in range(len(doc_text) - span_length + 1):
        window = doc_text[i: i + span_length]
        score = fuzz.ratio(span_text, window)

        if score > best_score:
            best_score = score
            best_offset = i

    if best_score >= threshold and best_offset is not None:
        return (best_offset, best_offset + span_length)

    return None


def validate_and_convert_annotations(
    raw_data: dict[str, Any],
    doc_text: str,
    doc_id: str,
    threshold: int = 90,
) -> AnnotationFile:
    """
    Validate span offsets, recover misaligned spans, and convert to AnnotationFile.

    Args:
        raw_data: Raw annotation data from LLM (with indices)
        doc_text: Full document text
        doc_id: Document ID
        threshold: Fuzzy matching threshold (0-100)

    Returns:
        AnnotationFile with validated spans and resolved references
    """
    raw_spans = raw_data.get("spans", [])
    raw_steps = raw_data.get("reasoning_steps", [])
    raw_anns = raw_data.get("document_annotations", [])

    # Validate and fix spans
    valid_spans = []
    invalid_span_indices: set[int] = set()

    for idx, raw_span in enumerate(raw_spans):
        if validate_span(raw_span, doc_text):
            # Exact match - keep as is
            valid_spans.append(raw_span)
        else:
            # Try fuzzy recovery
            recovered = recover_span_offsets(raw_span, doc_text, threshold)
            if recovered:
                new_start, new_end = recovered
                raw_span = dict(raw_span)
                raw_span["start"] = new_start
                raw_span["end"] = new_end
                valid_spans.append(raw_span)
                logger.info(f"Recovered span '{raw_span['text']}' at offset {new_start}")
            else:
                invalid_span_indices.add(idx)
                logger.warning(f"Discarded invalid span '{raw_span['text']}'")

    # Convert valid spans to Span objects with IDs and source='model'
    spans = [
        Span(
            start=s["start"],
            end=s["end"],
            text=s["text"],
            source="model",
        )
        for s in valid_spans
    ]

    # Build index mapping: old_index -> new span ID
    # valid spans are in order, skipping invalid indices
    valid_idx = 0
    span_id_map: dict[int, str] = {}
    for orig_idx in range(len(raw_spans)):
        if orig_idx not in invalid_span_indices:
            span_id_map[orig_idx] = spans[valid_idx].id
            valid_idx += 1

    # Convert reasoning steps, cleaning span references
    reasoning_steps = []
    for step_data in raw_steps:
        # Filter out invalid span indices
        valid_span_ids = [
            span_id_map[idx]
            for idx in step_data.get("span_indices", [])
            if idx not in invalid_span_indices and idx in span_id_map
        ]

        step = ReasoningStep(
            concept=Concept(
                code=step_data["concept_code"],
                display=step_data["concept_display"],
                system="SNOMED-CT",
            ),
            span_ids=valid_span_ids,
            note=step_data.get("note", ""),
            source="model",
        )
        reasoning_steps.append(step)

    # Build index mapping: old_index -> new step ID
    step_id_map = {i: reasoning_steps[i].id for i in range(len(reasoning_steps))}

    # Convert document annotations, cleaning span and step references
    document_annotations = []
    for ann_data in raw_anns:
        # Filter out invalid span indices
        valid_evidence_span_ids = [
            span_id_map[idx]
            for idx in ann_data.get("evidence_span_indices", [])
            if idx not in invalid_span_indices and idx in span_id_map
        ]

        # Filter step indices
        valid_step_ids = [
            step_id_map[idx]
            for idx in ann_data.get("reasoning_step_indices", [])
            if idx in step_id_map
        ]

        ann = DocumentAnnotation(
            concept=Concept(
                code=ann_data["concept_code"],
                display=ann_data["concept_display"],
                system="SNOMED-CT",
            ),
            evidence_span_ids=valid_evidence_span_ids,
            reasoning_step_ids=valid_step_ids,
            note=ann_data.get("note", ""),
            source="model",
        )
        document_annotations.append(ann)

    logger.info(
        f"Validation complete: {len(valid_spans)}/{len(raw_spans)} spans valid, "
        f"{len(invalid_span_indices)} discarded"
    )

    return AnnotationFile(
        doc_id=doc_id,
        spans=spans,
        reasoning_steps=reasoning_steps,
        document_annotations=document_annotations,
        completed=False,
    )
