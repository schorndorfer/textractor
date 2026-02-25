from __future__ import annotations

import logging
import os
from typing import Any

import anthropic
from rapidfuzz import fuzz

from .models import AnnotationFile, Concept, DocumentAnnotation, ReasoningStep, Span, TerminologyConcept

logger = logging.getLogger(__name__)


def _llm_runtime_context() -> str:
    bedrock_token_raw = os.environ.get("AWS_BEARER_TOKEN_BEDROCK")
    bedrock_token = bedrock_token_raw.strip() if bedrock_token_raw else ""
    auth_mode = "aws_bedrock" if bedrock_token else "direct_anthropic"
    model = os.environ.get("TEXTRACTOR_LLM_MODEL")
    model_desc = model if model else "<default>"
    return f"auth_mode={auth_mode}, model={model_desc}"


def _extract_tool_calls(response: Any, stage: str) -> list[Any]:
    response_content = getattr(response, "content", None)

    if not isinstance(response_content, list):
        context = _llm_runtime_context()
        stop_reason = getattr(response, "stop_reason", None)
        logger.error(
            "%s: invalid LLM content payload type=%s stop_reason=%s (%s)",
            stage,
            type(response_content).__name__,
            stop_reason,
            context,
        )

        response_error = getattr(response, "error", None)
        if response_error:
            response_summary = f"provider_error={response_error}"
        else:
            response_summary = f"response={repr(response)[:300]}"

        raise ValueError(
            f"LLM returned empty or invalid content ({context}). "
            f"Check TEXTRACTOR_LLM_MODEL is valid for the configured provider. {response_summary}"
        )

    tool_calls = [block for block in response_content if getattr(block, "type", None) == "tool_use"]

    if not tool_calls:
        logger.error(f"No tool calls found. stop_reason={response.stop_reason}, response={response}")
        raise ValueError("No tool calls found in LLM response")

    return tool_calls


def get_anthropic_client(api_key: str | None = None) -> anthropic.Anthropic:
    """
    Get the appropriate Anthropic client (direct API or AWS Bedrock).

    Checks for AWS Bedrock configuration via environment variables:
    - AWS_BEARER_TOKEN_BEDROCK: Bearer token for Bedrock authentication
    - AWS_REGION: AWS region for Bedrock (defaults to us-east-1)

    If bearer token is present, uses standard Anthropic client with custom headers.
    Otherwise, returns standard Anthropic client.

    Args:
        api_key: API key for direct Anthropic API (ignored for Bedrock bearer token auth)

    Returns:
        Anthropic client instance configured for direct API or Bedrock
    """
    bedrock_token_raw = os.environ.get("AWS_BEARER_TOKEN_BEDROCK")
    bedrock_token = bedrock_token_raw.strip() if bedrock_token_raw else ""

    if bedrock_token.lower().startswith("bearer "):
        bedrock_token = bedrock_token[7:].strip()

    if bedrock_token:
        # Use AWS Bedrock with bearer token authentication
        # Note: The official AnthropicBedrock client doesn't support bearer tokens yet
        # (PR #1129 is pending), so we use the standard client with custom configuration
        aws_region = os.environ.get("AWS_REGION", "us-east-1")
        bedrock_base_url = f"https://bedrock-runtime.{aws_region}.amazonaws.com"

        logger.info(
            "LLM auth mode: aws_bedrock_bearer_token, region=%s, token_length=%s",
            aws_region,
            len(bedrock_token),
        )

        return anthropic.Anthropic(
            base_url=bedrock_base_url,
            api_key="bedrock",  # Dummy value, not used with bearer token
            default_headers={
                "Authorization": f"Bearer {bedrock_token}",
            },
        )
    else:
        # Use direct Anthropic API
        logger.info("LLM auth mode: direct_anthropic_api")
        return anthropic.Anthropic(api_key=api_key)

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
    client = get_anthropic_client(api_key=api_key)

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

    max_tokens = int(os.environ.get("TEXTRACTOR_LLM_MAX_TOKENS_EXTRACT", "4096"))
    temperature = float(os.environ.get("TEXTRACTOR_LLM_TEMPERATURE", "0.0"))

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        tools=tools,
        messages=[{"role": "user", "content": prompt}],
    )

    logger.info(f"Term extraction: stop_reason={response.stop_reason}, usage={response.usage}")

    # Check for tool calls first
    tool_calls = _extract_tool_calls(response, stage="term_extraction")

    # Accept tool_use or max_tokens if we have a valid tool call
    if response.stop_reason not in ("tool_use", "max_tokens"):
        logger.error(f"LLM stop_reason was '{response.stop_reason}', expected 'tool_use' or 'max_tokens'. Response: {response}")
        raise ValueError(f"LLM did not return structured output (stop_reason: {response.stop_reason})")

    if response.stop_reason == "max_tokens":
        logger.warning(f"Term extraction hit max_tokens limit but found valid tool call, proceeding anyway")

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
    client = get_anthropic_client(api_key=api_key)

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
                                "span_indices": {
                                    "type": "array",
                                    "items": {"type": "integer"},
                                    "minItems": 1,
                                },
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
                                "reasoning_step_indices": {
                                    "type": "array",
                                    "items": {"type": "integer"},
                                    "minItems": 1,
                                },
                                "note": {"type": "string"},
                                "category": {
                                    "type": "string",
                                    "enum": [
                                        "problem", "procedure", "medication", "lab", "symptom",
                                        "diagnosis", "finding", "sign", "device", "allergy",
                                        "demographic", "administrative", "temporal",
                                        "social_history", "other"
                                    ],
                                },
                            },
                            "required": ["concept_code", "concept_display", "category", "reasoning_step_indices"],
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
5. STRICT HIERARCHY - follow this progression:
   - Spans (text evidence) → Reasoning Steps (intermediate concepts) → Document Annotations (final findings)
   - Every reasoning step MUST reference at least 1 span
   - Every document annotation MUST reference at least 1 reasoning step
   - Document annotations should NOT directly reference spans - only through reasoning steps
6. Use span_indices and reasoning_step_indices to reference items by array position (0-indexed)
7. Categorize each document annotation:
   - problem/diagnosis/finding: diseases, conditions, disorders
   - symptom/sign: patient complaints, clinical observations
   - procedure: therapeutic/diagnostic procedures
   - medication: drugs, pharmaceuticals
   - lab: laboratory tests and results
   - device: medical devices, implants
   - allergy: allergic reactions, intolerances
   - demographic: age, gender, race (NON-clinical)
   - administrative: visit info, insurance (NON-clinical)
   - social_history: smoking, alcohol (NON-clinical)
   - temporal: dates, times (NON-clinical)
   - other: anything else
8. Be accurate - only annotate what is clearly stated in the text

Return structured annotations following the tool schema."""

    max_tokens = int(os.environ.get("TEXTRACTOR_LLM_MAX_TOKENS_ANNOTATE", "16384"))
    temperature = float(os.environ.get("TEXTRACTOR_LLM_TEMPERATURE", "0.0"))

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        tools=tools,
        messages=[{"role": "user", "content": prompt}],
    )

    logger.info(f"Annotation generation: stop_reason={response.stop_reason}, usage={response.usage}")

    # Check for tool calls first
    tool_calls = _extract_tool_calls(response, stage="annotation_generation")

    # Accept tool_use or max_tokens if we have a valid tool call
    if response.stop_reason not in ("tool_use", "max_tokens"):
        logger.error(f"LLM stop_reason was '{response.stop_reason}', expected 'tool_use' or 'max_tokens'. Response: {response}")
        raise ValueError(f"LLM did not return structured output (stop_reason: {response.stop_reason})")

    if response.stop_reason == "max_tokens":
        logger.warning(f"Annotation generation hit max_tokens limit but found valid tool call, proceeding anyway")

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
            category=ann_data.get("category"),
        )
        document_annotations.append(ann)

    logger.info(
        f"Validation complete: {len(valid_spans)}/{len(raw_spans)} spans valid, "
        f"{len(invalid_span_indices)} discarded"
    )

    # ===== HIERARCHY VALIDATION =====

    # Stage 1: Filter reasoning steps with no spans
    hierarchy_valid_steps = []
    filtered_steps_no_spans = 0

    for step in reasoning_steps:
        if len(step.span_ids) == 0:
            filtered_steps_no_spans += 1
            logger.info(f"Hierarchy: filtered reasoning step with no spans: {step.concept.display}")
        else:
            hierarchy_valid_steps.append(step)

    reasoning_steps = hierarchy_valid_steps

    # Rebuild valid step ID set for Stage 2
    valid_step_ids = {step.id for step in reasoning_steps}

    # Stage 2: Filter document annotations with direct span links or no valid reasoning steps
    hierarchy_valid_anns = []
    filtered_anns_no_steps = 0
    filtered_anns_direct_spans = 0

    for ann in document_annotations:
        # Check for direct span links (should be empty for AI-generated annotations)
        if len(ann.evidence_span_ids) > 0:
            filtered_anns_direct_spans += 1
            logger.info(f"Hierarchy: filtered annotation with direct span links: {ann.concept.display}")
            continue

        # Check that annotation references at least one still-valid reasoning step
        valid_referenced_steps = [sid for sid in ann.reasoning_step_ids if sid in valid_step_ids]
        if len(valid_referenced_steps) == 0:
            filtered_anns_no_steps += 1
            logger.info(f"Hierarchy: filtered annotation with no valid reasoning steps: {ann.concept.display}")
            continue

        hierarchy_valid_anns.append(ann)

    document_annotations = hierarchy_valid_anns

    if filtered_steps_no_spans > 0 or filtered_anns_no_steps > 0 or filtered_anns_direct_spans > 0:
        logger.info(
            f"Hierarchy validation: filtered {filtered_steps_no_spans} reasoning steps (no spans), "
            f"{filtered_anns_no_steps} document annotations (no reasoning steps), "
            f"{filtered_anns_direct_spans} document annotations (direct span links)"
        )

    # ===== END HIERARCHY VALIDATION STAGE 1 =====

    # Stage 1: Filter non-clinical document annotations
    clinical_annotations = []
    filtered_count = 0
    filtered_by_category: dict[str, int] = {}

    for ann in document_annotations:
        category = ann.category or "unknown"
        if category in CLINICAL_CATEGORIES:
            clinical_annotations.append(ann)
        else:
            filtered_count += 1
            filtered_by_category[category] = filtered_by_category.get(category, 0) + 1
            logger.info(f"Filtered out {category} annotation: {ann.concept.display}")

    # Stage 2: Remove orphaned reasoning steps
    referenced_step_ids = set()
    for ann in clinical_annotations:
        referenced_step_ids.update(ann.reasoning_step_ids)

    clinical_steps = [step for step in reasoning_steps if step.id in referenced_step_ids]
    orphaned_steps = len(reasoning_steps) - len(clinical_steps)

    # Stage 3: Remove orphaned spans
    referenced_span_ids = set()
    for step in clinical_steps:
        referenced_span_ids.update(step.span_ids)

    clinical_spans = [span for span in spans if span.id in referenced_span_ids]
    orphaned_spans = len(spans) - len(clinical_spans)

    if filtered_count > 0:
        category_summary = ", ".join(f"{cat}={count}" for cat, count in filtered_by_category.items())
        logger.info(
            f"Clinical filtering: kept {len(clinical_annotations)}/{len(document_annotations)} annotations, "
            f"removed {filtered_count} non-clinical ({category_summary}), "
            f"cascaded removal: {orphaned_steps} reasoning steps, {orphaned_spans} spans"
        )

    return AnnotationFile(
        doc_id=doc_id,
        spans=clinical_spans,
        reasoning_steps=clinical_steps,
        document_annotations=clinical_annotations,
        completed=False,
    )
