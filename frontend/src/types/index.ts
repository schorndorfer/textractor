export interface Concept {
  code: string;
  display: string;
  system: string;
}

export interface Span {
  id: string;
  start: number;
  end: number;
  text: string;
}

export interface ReasoningStep {
  id: string;
  concept: Concept;
  span_ids: string[];
  note?: string;
}

export interface DocumentAnnotation {
  id: string;
  concept: Concept;
  evidence_span_ids: string[];
  reasoning_step_ids: string[];
  note?: string;
}

export interface AnnotationFile {
  doc_id: string;
  spans: Span[];
  reasoning_steps: ReasoningStep[];
  document_annotations: DocumentAnnotation[];
}

export interface Document {
  id: string;
  text: string;
  metadata: Record<string, unknown>;
}

export interface DocumentSummary {
  id: string;
  metadata: Record<string, unknown>;
  is_annotated: boolean;
  text_preview: string;
}

export interface TerminologyConcept {
  code: string;
  display: string;
  system: string;
}

export interface TerminologyInfo {
  total_concepts: number;
  file_name: string | null;
  loaded: boolean;
}
