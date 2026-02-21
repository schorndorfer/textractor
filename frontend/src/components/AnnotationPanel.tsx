import type { AnnotationFile, DocumentAnnotation, ReasoningStep, Span } from '../types';
import type { SpanColorMap } from '../App';
import { DocumentAnnotationList } from './DocumentAnnotationList';
import { ReasoningStepList } from './ReasoningStepList';
import { SpanList } from './SpanList';

interface Props {
  annotations: AnnotationFile;
  onChange: (ann: AnnotationFile) => void;
  onSave: () => void;
  isDirty: boolean;
  saveError: string | null;
  spanColorMap: SpanColorMap;
  docAnnColorMap: SpanColorMap;
  stepColorMap: SpanColorMap;
  selectedAnnotationId: string | null;
  onAnnotationSelect: (annotationId: string | null) => void;
  onToggleCollapse?: () => void;
  collapsed?: boolean;
}

export function AnnotationPanel({
  annotations,
  onChange,
  onSave,
  isDirty,
  saveError,
  spanColorMap,
  docAnnColorMap,
  stepColorMap,
  selectedAnnotationId,
  onAnnotationSelect,
  onToggleCollapse,
  collapsed,
}: Props) {
  const updateSpans = (spans: Span[]) => {
    // Cascade: remove deleted span IDs from steps and doc annotations
    const spanIds = new Set(spans.map((s) => s.id));
    const steps = annotations.reasoning_steps.map((step) => ({
      ...step,
      span_ids: step.span_ids.filter((id) => spanIds.has(id)),
    }));
    const docAnns = annotations.document_annotations.map((ann) => ({
      ...ann,
      evidence_span_ids: ann.evidence_span_ids.filter((id) => spanIds.has(id)),
    }));
    onChange({ ...annotations, spans, reasoning_steps: steps, document_annotations: docAnns });
  };

  const updateSteps = (steps: ReasoningStep[]) => {
    // Cascade: remove deleted step IDs from doc annotations
    const stepIds = new Set(steps.map((s) => s.id));
    const docAnns = annotations.document_annotations.map((ann) => ({
      ...ann,
      reasoning_step_ids: ann.reasoning_step_ids.filter((id) => stepIds.has(id)),
    }));
    onChange({ ...annotations, reasoning_steps: steps, document_annotations: docAnns });
  };

  const updateDocAnns = (docAnns: DocumentAnnotation[]) =>
    onChange({ ...annotations, document_annotations: docAnns });

  return (
    <aside className="annotation-panel">
      <div className="panel-header">
        {onToggleCollapse && (
          <button
            className="sidebar-toggle"
            onClick={onToggleCollapse}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            ›
          </button>
        )}
        <h2>Annotations</h2>
        <button onClick={onSave} disabled={!isDirty} className={`save-btn${isDirty ? ' dirty' : ''}`}>
          Save
        </button>
      </div>
      {saveError && <p className="save-error">{saveError}</p>}

      <section className="panel-section">
        <h3>Spans ({annotations.spans.length})</h3>
        <SpanList spans={annotations.spans} onChange={updateSpans} spanColorMap={spanColorMap} />
      </section>

      <section className="panel-section">
        <h3>Reasoning Steps ({annotations.reasoning_steps.length})</h3>
        <ReasoningStepList
          steps={annotations.reasoning_steps}
          availableSpans={annotations.spans}
          onChange={updateSteps}
          stepColorMap={stepColorMap}
          selectedAnnotationId={selectedAnnotationId}
          annotations={annotations.document_annotations}
        />
      </section>

      <section className="panel-section">
        <h3>Document Annotations ({annotations.document_annotations.length})</h3>
        <DocumentAnnotationList
          annotations={annotations.document_annotations}
          availableSpans={annotations.spans}
          availableSteps={annotations.reasoning_steps}
          onChange={updateDocAnns}
          docAnnColorMap={docAnnColorMap}
          selectedAnnotationId={selectedAnnotationId}
          onAnnotationSelect={onAnnotationSelect}
        />
      </section>
    </aside>
  );
}
