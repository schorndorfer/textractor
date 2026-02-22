/**
 * Color mapping utilities for document annotations, reasoning steps, and spans
 */

import type { AnnotationFile } from '../types';
import { COLOR_PALETTE } from '../constants';

export type ColorMap = Map<string, { bg: string; border: string }>;

export interface ColorMappings {
  spanColorMap: ColorMap;
  docAnnColorMap: ColorMap;
  stepColorMap: ColorMap;
}

/**
 * Compute color mappings for document annotations, spans, and reasoning steps.
 *
 * Document annotations are assigned colors from the palette in order.
 * Spans and reasoning steps inherit colors from their parent document annotations.
 *
 * @param annotations - The annotation file containing all annotations
 * @returns Object containing color maps for spans, document annotations, and steps
 */
export function computeColorMappings(
  annotations: AnnotationFile | null
): ColorMappings {
  const spanMap = new Map<string, { bg: string; border: string }>();
  const docAnnMap = new Map<string, { bg: string; border: string }>();
  const stepMap = new Map<string, { bg: string; border: string }>();

  if (!annotations) {
    return { spanColorMap: spanMap, docAnnColorMap: docAnnMap, stepColorMap: stepMap };
  }

  // Assign colors to document annotations
  annotations.document_annotations.forEach((ann, idx) => {
    docAnnMap.set(ann.id, COLOR_PALETTE[idx % COLOR_PALETTE.length]);
  });

  // Map spans and reasoning steps to colors via document annotations
  annotations.document_annotations.forEach((ann) => {
    const color = docAnnMap.get(ann.id);
    if (!color) return;

    // Direct evidence spans
    ann.evidence_span_ids.forEach((spanId) => {
      if (!spanMap.has(spanId)) {
        spanMap.set(spanId, color);
      }
    });

    // Reasoning steps
    ann.reasoning_step_ids.forEach((stepId) => {
      if (!stepMap.has(stepId)) {
        stepMap.set(stepId, color);
      }

      // Indirect spans via reasoning steps
      const step = annotations.reasoning_steps.find((s) => s.id === stepId);
      if (step) {
        step.span_ids.forEach((spanId) => {
          if (!spanMap.has(spanId)) {
            spanMap.set(spanId, color);
          }
        });
      }
    });
  });

  return { spanColorMap: spanMap, docAnnColorMap: docAnnMap, stepColorMap: stepMap };
}
