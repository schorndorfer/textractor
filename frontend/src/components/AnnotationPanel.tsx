import type { AnnotationFile, DocumentAnnotation, ReasoningStep, Span } from '../types';
import type { SpanColorMap } from '../App';
import { DocumentAnnotationList } from './DocumentAnnotationList';
import { ReasoningStepList } from './ReasoningStepList';
import { SpanList } from './SpanList';

interface Props {
  annotations: AnnotationFile;
  onChange: (ann: AnnotationFile) => void;
  onRevert: () => void;
  isDirty: boolean;
  saveError: string | null;
  spanColorMap: SpanColorMap;
  docAnnColorMap: SpanColorMap;
  stepColorMap: SpanColorMap;
  selectedAnnotationId: string | null;
  onAnnotationSelect: (annotationId: string | null) => void;
  onToggleCollapse?: () => void;
  collapsed?: boolean;
  onSpanClick?: (spanId: string) => void;
  onPreAnnotate: () => void;
  isPreAnnotating: boolean;
  preAnnotateError: string | null;
}

export function AnnotationPanel({
  annotations,
  onChange,
  onRevert,
  isDirty,
  saveError,
  spanColorMap,
  docAnnColorMap,
  stepColorMap,
  selectedAnnotationId,
  onAnnotationSelect,
  onToggleCollapse,
  collapsed,
  onSpanClick,
  onPreAnnotate,
  isPreAnnotating,
  preAnnotateError,
}: Props) {
  const isLocked = annotations.completed;

  const updateSpans = (spans: Span[]) => {
    if (isLocked) return; // Prevent edits when completed
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
    if (isLocked) return; // Prevent edits when completed
    // Cascade: remove deleted step IDs from doc annotations
    const stepIds = new Set(steps.map((s) => s.id));
    const docAnns = annotations.document_annotations.map((ann) => ({
      ...ann,
      reasoning_step_ids: ann.reasoning_step_ids.filter((id) => stepIds.has(id)),
    }));
    onChange({ ...annotations, reasoning_steps: steps, document_annotations: docAnns });
  };

  const updateDocAnns = (docAnns: DocumentAnnotation[]) => {
    if (isLocked) return; // Prevent edits when completed
    onChange({ ...annotations, document_annotations: docAnns });
  };

  const toggleCompleted = () => {
    onChange({ ...annotations, completed: !annotations.completed });
  };

  const handlePreAnnotate = () => {
    const hasExistingAnnotations =
      annotations.spans.length > 0 ||
      annotations.reasoning_steps.length > 0 ||
      annotations.document_annotations.length > 0;

    if (hasExistingAnnotations) {
      const confirmed = window.confirm(
        'This will replace all existing annotations with AI-generated content. Continue?'
      );
      if (!confirmed) return;
    }

    onPreAnnotate();
  };

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
        <h2>
          Annotations {isLocked && <span className="lock-icon" title="Document is locked">🔒</span>}
        </h2>
        <button
          onClick={handlePreAnnotate}
          disabled={isLocked || isPreAnnotating}
          className="preannotate-btn"
          title="Generate AI annotations"
        >
          {isPreAnnotating ? '⏳ Pre-annotating...' : '✨ Pre-annotate'}
        </button>
        <button onClick={onRevert} disabled={!isDirty || isLocked} className={`save-btn${isDirty ? ' dirty' : ''}`}>
          Revert
        </button>
        <label className="completed-checkbox">
          <input
            type="checkbox"
            checked={annotations.completed || false}
            onChange={toggleCompleted}
          />
          <span>Completed</span>
        </label>
      </div>
      {isPreAnnotating && (
        <div className="preannotate-loading">
          ⏳ Generating AI annotations... This may take a moment.
        </div>
      )}
      {(saveError || preAnnotateError) && !isLocked && (
        <p className="save-error">{saveError || preAnnotateError}</p>
      )}
      {isLocked && (
        <div className="locked-notice">
          <p>🔒 This document is locked. Uncheck "Completed" to make changes.</p>
        </div>
      )}

      <section className="panel-section">
        <h3>Spans ({annotations.spans.length})</h3>
        <SpanList spans={annotations.spans} onChange={updateSpans} spanColorMap={spanColorMap} onSpanClick={onSpanClick} disabled={isLocked} />
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
          disabled={isLocked}
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
          disabled={isLocked}
        />
      </section>
    </aside>
  );
}
