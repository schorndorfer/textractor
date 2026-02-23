import { useState, useMemo, useEffect } from 'react';
import type { ReasoningStep, Span, TerminologyConcept, DocumentAnnotation } from '../types';
import type { SpanColorMap } from '../App';
import { ConceptSearch } from './ConceptSearch';

function randomId(prefix: string) {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

interface Props {
  steps: ReasoningStep[];
  availableSpans: Span[];
  onChange: (steps: ReasoningStep[]) => void;
  stepColorMap: SpanColorMap;
  selectedAnnotationId: string | null;
  annotations: DocumentAnnotation[];
  onAnnotationSelect: (annotationId: string | null) => void;
  disabled?: boolean;
}

export function ReasoningStepList({ steps, availableSpans, onChange, stepColorMap, selectedAnnotationId, annotations, onAnnotationSelect, disabled }: Props) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftConcept, setDraftConcept] = useState<TerminologyConcept | null>(null);
  const [draftSpanIds, setDraftSpanIds] = useState<string[]>([]);
  const [draftNote, setDraftNote] = useState<string>('');

  // Close any open edits when document becomes locked
  useEffect(() => {
    if (disabled && editingId) {
      setEditingId(null);
    }
  }, [disabled, editingId]);

  // Compute which steps are selected (related to the selected document annotation)
  const selectedStepIds = useMemo(() => {
    if (!selectedAnnotationId) return new Set<string>();
    const selectedAnn = annotations.find((a) => a.id === selectedAnnotationId);
    return new Set(selectedAnn?.reasoning_step_ids || []);
  }, [selectedAnnotationId, annotations]);

  const addStep = () => {
    if (disabled) return;
    const id = randomId('step');
    const newStep: ReasoningStep = {
      id,
      concept: { code: '', display: '', system: 'SNOMED-CT' },
      span_ids: [],
      note: '',
      source: 'human',
    };
    onChange([...steps, newStep]);
    setEditingId(id);
    setDraftConcept(null);
    setDraftSpanIds([]);
    setDraftNote('');
  };

  const commitEdit = (stepId: string) => {
    if (!draftConcept) return;

    onChange(
      steps.map((s) => {
        if (s.id !== stepId) return s;

        const conceptChanged =
          s.concept.code !== draftConcept.code ||
          s.concept.display !== draftConcept.display;

        const spanIdsChanged =
          JSON.stringify([...s.span_ids].sort()) !== JSON.stringify([...draftSpanIds].sort());

        const substantiveEdit = conceptChanged || spanIdsChanged;

        return {
          ...s,
          concept: draftConcept,
          span_ids: draftSpanIds,
          note: draftNote,
          source: substantiveEdit ? 'human' : s.source,
        };
      })
    );
    setEditingId(null);
  };

  const cancelEdit = (stepId: string) => {
    // If the step has no concept yet (newly added, never committed), remove it
    const step = steps.find((s) => s.id === stepId);
    if (step && !step.concept.code) {
      onChange(steps.filter((s) => s.id !== stepId));
    }
    setEditingId(null);
  };

  const deleteStep = (id: string) => {
    onChange(steps.filter((s) => s.id !== id));
    if (editingId === id) setEditingId(null);
  };

  const toggleSpan = (spanId: string) => {
    setDraftSpanIds((prev) =>
      prev.includes(spanId) ? prev.filter((id) => id !== spanId) : [...prev, spanId]
    );
  };

  const handleStepClick = (stepId: string) => {
    if (disabled) return;

    // Find document annotation(s) that reference this step
    const parentAnns = annotations.filter((ann) =>
      ann.reasoning_step_ids.includes(stepId)
    );

    if (parentAnns.length === 0) return; // No parent annotation

    // Toggle behavior: if current selection includes this step, deselect
    if (selectedAnnotationId && parentAnns.some((ann) => ann.id === selectedAnnotationId)) {
      onAnnotationSelect(selectedAnnotationId); // Toggle off (will switch to document tab)
      return;
    }

    // Select the first parent annotation
    onAnnotationSelect(parentAnns[0].id);
  };

  return (
    <div className="item-list">
      {steps.map((step) => {
        const color = stepColorMap.get(step.id);
        const isSelected = selectedStepIds.has(step.id);
        return (
          <div
            key={step.id}
            className={`list-item${editingId === step.id ? ' editing' : ''}${isSelected ? ' selected' : ''}`}
          >
            {editingId === step.id ? (
              <div className="edit-form">
                <ConceptSearch
                  value={draftConcept}
                  onChange={setDraftConcept}
                  placeholder="Search for intermediate concept..."
                />
                <div className="form-field">
                  <label>Note (optional):</label>
                  <textarea
                    value={draftNote}
                    onChange={(e) => setDraftNote(e.target.value)}
                    placeholder="Add free-form notes about this reasoning step..."
                    rows={3}
                  />
                </div>
                {availableSpans.length > 0 && (
                  <div className="checkbox-group">
                    <label className="checkbox-group-label">Link spans:</label>
                    {availableSpans.map((span) => (
                      <label key={span.id} className="checkbox-item">
                        <input
                          type="checkbox"
                          checked={draftSpanIds.includes(span.id)}
                          onChange={() => toggleSpan(span.id)}
                        />
                        <span>"{span.text}"</span>
                      </label>
                    ))}
                  </div>
                )}
                <div className="edit-actions">
                  <button
                    onClick={() => commitEdit(step.id)}
                    disabled={!draftConcept}
                    className="btn-primary"
                  >
                    Confirm
                  </button>
                  <button onClick={() => cancelEdit(step.id)} className="btn-secondary">
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="item-row" onClick={() => handleStepClick(step.id)}>
                {color && (
                  <span
                    className="color-indicator"
                    style={{ backgroundColor: color.border }}
                    title="Linked to document annotation"
                  />
                )}
                <div className="item-info">
                  <span className="concept-label">
                    {step.source === 'model' && (
                      <span className="ai-badge" title="Model-generated">✨</span>
                    )}
                    {step.concept.display || '(no concept)'}{' '}
                    {step.concept.code && (
                      <span className="concept-code">[{step.concept.code}]</span>
                    )}
                  </span>
                  {step.note && <div className="item-note">{step.note}</div>}
                  <span className="item-meta">{step.span_ids.length} span(s) linked</span>
                </div>
                {!disabled && (
                  <div className="item-actions">
                    <button
                      onClick={() => {
                        setEditingId(step.id);
                        setDraftConcept(step.concept.code ? step.concept : null);
                        setDraftSpanIds(step.span_ids);
                        setDraftNote(step.note || '');
                      }}
                      className="btn-small"
                    >
                      Edit
                    </button>
                    <button onClick={() => deleteStep(step.id)} className="btn-small btn-danger">
                      Delete
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
      {!disabled && (
        <button onClick={addStep} className="btn-add">
          + Add Reasoning Step
        </button>
      )}
    </div>
  );
}
