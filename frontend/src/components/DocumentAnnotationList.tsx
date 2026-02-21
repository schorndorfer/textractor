import { useState } from 'react';
import type { DocumentAnnotation, ReasoningStep, Span, TerminologyConcept } from '../types';
import type { SpanColorMap } from '../App';
import { ConceptSearch } from './ConceptSearch';

function randomId(prefix: string) {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

interface Props {
  annotations: DocumentAnnotation[];
  availableSpans: Span[];
  availableSteps: ReasoningStep[];
  onChange: (anns: DocumentAnnotation[]) => void;
  docAnnColorMap: SpanColorMap;
  selectedAnnotationId: string | null;
  onAnnotationSelect: (annotationId: string | null) => void;
}

export function DocumentAnnotationList({
  annotations,
  availableSpans,
  availableSteps,
  onChange,
  docAnnColorMap,
  selectedAnnotationId,
  onAnnotationSelect,
}: Props) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftConcept, setDraftConcept] = useState<TerminologyConcept | null>(null);
  const [draftSpanIds, setDraftSpanIds] = useState<string[]>([]);
  const [draftStepIds, setDraftStepIds] = useState<string[]>([]);

  const addAnnotation = () => {
    const id = randomId('ann');
    const newAnn: DocumentAnnotation = {
      id,
      concept: { code: '', display: '', system: 'SNOMED-CT' },
      evidence_span_ids: [],
      reasoning_step_ids: [],
    };
    onChange([...annotations, newAnn]);
    setEditingId(id);
    setDraftConcept(null);
    setDraftSpanIds([]);
    setDraftStepIds([]);
  };

  const commitEdit = (annId: string) => {
    if (!draftConcept) return;
    onChange(
      annotations.map((a) =>
        a.id === annId
          ? {
              ...a,
              concept: draftConcept,
              evidence_span_ids: draftSpanIds,
              reasoning_step_ids: draftStepIds,
            }
          : a
      )
    );
    setEditingId(null);
  };

  const cancelEdit = (annId: string) => {
    const ann = annotations.find((a) => a.id === annId);
    if (ann && !ann.concept.code) {
      onChange(annotations.filter((a) => a.id !== annId));
    }
    setEditingId(null);
  };

  const deleteAnnotation = (id: string) => {
    onChange(annotations.filter((a) => a.id !== id));
    if (editingId === id) setEditingId(null);
  };

  const toggleId = (id: string, current: string[], setter: (ids: string[]) => void) => {
    setter(current.includes(id) ? current.filter((x) => x !== id) : [...current, id]);
  };

  return (
    <div className="item-list">
      {annotations.map((ann) => {
        const color = docAnnColorMap.get(ann.id);
        const isSelected = selectedAnnotationId === ann.id;
        return (
          <div
            key={ann.id}
            className={`list-item${editingId === ann.id ? ' editing' : ''}${isSelected ? ' selected' : ''}`}
          >
            {editingId === ann.id ? (
              <div className="edit-form">
              <ConceptSearch
                value={draftConcept}
                onChange={setDraftConcept}
                placeholder="Search for document-level concept..."
              />
              {availableSpans.length > 0 && (
                <div className="checkbox-group">
                  <label className="checkbox-group-label">Evidence spans:</label>
                  {availableSpans.map((span) => (
                    <label key={span.id} className="checkbox-item">
                      <input
                        type="checkbox"
                        checked={draftSpanIds.includes(span.id)}
                        onChange={() => toggleId(span.id, draftSpanIds, setDraftSpanIds)}
                      />
                      <span>"{span.text}"</span>
                    </label>
                  ))}
                </div>
              )}
              {availableSteps.length > 0 && (
                <div className="checkbox-group">
                  <label className="checkbox-group-label">Reasoning steps:</label>
                  {availableSteps.map((step) => (
                    <label key={step.id} className="checkbox-item">
                      <input
                        type="checkbox"
                        checked={draftStepIds.includes(step.id)}
                        onChange={() => toggleId(step.id, draftStepIds, setDraftStepIds)}
                      />
                      <span>{step.concept.display || step.id}</span>
                    </label>
                  ))}
                </div>
              )}
              <div className="edit-actions">
                <button
                  onClick={() => commitEdit(ann.id)}
                  disabled={!draftConcept}
                  className="btn-primary"
                >
                  Confirm
                </button>
                <button onClick={() => cancelEdit(ann.id)} className="btn-secondary">
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="item-row" onClick={() => onAnnotationSelect(ann.id)}>
              {color && (
                <span
                  className="color-indicator"
                  style={{ backgroundColor: color.border }}
                  title="Document annotation color"
                />
              )}
              <div className="item-info">
                <span className="concept-label">
                  {ann.concept.display || '(no concept)'}{' '}
                  {ann.concept.code && (
                    <span className="concept-code">[{ann.concept.code}]</span>
                  )}
                </span>
                <span className="item-meta">
                  {ann.evidence_span_ids.length} span(s), {ann.reasoning_step_ids.length} step(s)
                </span>
              </div>
              <div className="item-actions" onClick={(e) => e.stopPropagation()}>
                <button
                  onClick={() => {
                    setEditingId(ann.id);
                    setDraftConcept(ann.concept.code ? ann.concept : null);
                    setDraftSpanIds(ann.evidence_span_ids);
                    setDraftStepIds(ann.reasoning_step_ids);
                  }}
                  className="btn-small"
                >
                  Edit
                </button>
                <button
                  onClick={() => deleteAnnotation(ann.id)}
                  className="btn-small btn-danger"
                >
                  Delete
                </button>
              </div>
            </div>
          )}
          </div>
        );
      })}
      <button onClick={addAnnotation} className="btn-add">
        + Add Document Annotation
      </button>
    </div>
  );
}
