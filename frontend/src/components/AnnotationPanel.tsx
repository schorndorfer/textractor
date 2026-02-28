import { useState } from 'react';
import type { AnnotationFile, DocumentAnnotation, ReasoningStep, Span } from '../types';
import type { SpanColorMap } from '../App';
import { DocumentAnnotationList } from './DocumentAnnotationList';
import { ReasoningStepList } from './ReasoningStepList';
import { SpanList } from './SpanList';

interface Props {
  annotations: AnnotationFile;
  onChange: (ann: AnnotationFile) => void;
  onUndo: () => void;
  canUndo: boolean;
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
  terminologySystem: string;
  onTerminologyChange: (system: string) => void;
  availableSystems: string[];
}

export function AnnotationPanel({
  annotations,
  onChange,
  onUndo,
  canUndo,
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
  terminologySystem,
  onTerminologyChange,
  availableSystems,
}: Props) {
  const isLocked = annotations.completed;
  const [collapsedSections, setCollapsedSections] = useState<Set<string>>(new Set());

  const toggleSection = (section: string) => {
    setCollapsedSections((prev) => {
      const next = new Set(prev);
      if (next.has(section)) {
        next.delete(section);
      } else {
        next.add(section);
      }
      return next;
    });
  };

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

  const handleClear = () => {
    const hasExistingAnnotations =
      annotations.spans.length > 0 ||
      annotations.reasoning_steps.length > 0 ||
      annotations.document_annotations.length > 0;

    if (!hasExistingAnnotations) return; // Nothing to clear

    const confirmed = window.confirm(
      'This will delete all annotations (spans, reasoning steps, and document annotations). This cannot be undone. Continue?'
    );

    if (!confirmed) return;

    onChange({
      ...annotations,
      spans: [],
      reasoning_steps: [],
      document_annotations: [],
    });
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
          <span className="sidebar-icon sidebar-icon--orange" title="Annotations">✏</span> {isLocked && <span className="lock-icon" title="Document is locked">🔒</span>}
        </h2>
        <select
          className="terminology-selector"
          value={terminologySystem}
          onChange={(e) => onTerminologyChange(e.target.value)}
          disabled={availableSystems.length <= 1}
          title="Select terminology system"
        >
          {availableSystems.map((sys) => (
            <option key={sys} value={sys}>{sys}</option>
          ))}
        </select>
        <div className="header-actions">
          <button
            onClick={handlePreAnnotate}
            disabled={isLocked || isPreAnnotating}
            className="preannotate-btn"
            title={isPreAnnotating ? 'Generating AI annotations…' : 'Generate AI annotations'}
          >
            {isPreAnnotating ? '⏳' : '⚙'} Pre-annotate
          </button>
          <button
            onClick={handleClear}
            disabled={
              isLocked ||
              (annotations.spans.length === 0 &&
                annotations.reasoning_steps.length === 0 &&
                annotations.document_annotations.length === 0)
            }
            className="icon-btn icon-clear"
            title="Clear all annotations"
          >
            🗑
          </button>
          <button
            onClick={onUndo}
            disabled={!canUndo || isLocked}
            className={`icon-btn icon-undo${canUndo ? ' active' : ''}`}
            title="Undo last change"
          >
            ↩
          </button>
        </div>
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
          <p>🔒 This document is locked. Use the lock toggle in the document list to unlock and edit.</p>
        </div>
      )}

      <section className={`panel-section${collapsedSections.has('spans') ? ' collapsed' : ''}`}>
        <h3 onClick={() => toggleSection('spans')}>
          <span>Spans ({annotations.spans.length})</span>
          <span className={`section-chevron${collapsedSections.has('spans') ? ' collapsed' : ''}`}>▼</span>
        </h3>
        <SpanList spans={annotations.spans} onChange={updateSpans} spanColorMap={spanColorMap} onSpanClick={onSpanClick} disabled={isLocked} />
      </section>

      <section className={`panel-section${collapsedSections.has('steps') ? ' collapsed' : ''}`}>
        <h3 onClick={() => toggleSection('steps')}>
          <span>Reasoning Steps ({annotations.reasoning_steps.length})</span>
          <span className={`section-chevron${collapsedSections.has('steps') ? ' collapsed' : ''}`}>▼</span>
        </h3>
        <ReasoningStepList
          steps={annotations.reasoning_steps}
          availableSpans={annotations.spans}
          onChange={updateSteps}
          stepColorMap={stepColorMap}
          selectedAnnotationId={selectedAnnotationId}
          annotations={annotations.document_annotations}
          onAnnotationSelect={onAnnotationSelect}
          disabled={isLocked}
          system={terminologySystem}
        />
      </section>

      <section className={`panel-section${collapsedSections.has('annotations') ? ' collapsed' : ''}`}>
        <h3 onClick={() => toggleSection('annotations')}>
          <span>Document Annotations ({annotations.document_annotations.length})</span>
          <span className={`section-chevron${collapsedSections.has('annotations') ? ' collapsed' : ''}`}>▼</span>
        </h3>
        <DocumentAnnotationList
          annotations={annotations.document_annotations}
          availableSpans={annotations.spans}
          availableSteps={annotations.reasoning_steps}
          onChange={updateDocAnns}
          docAnnColorMap={docAnnColorMap}
          selectedAnnotationId={selectedAnnotationId}
          onAnnotationSelect={onAnnotationSelect}
          disabled={isLocked}
          system={terminologySystem}
        />
      </section>
    </aside>
  );
}
