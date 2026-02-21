import { useState } from 'react';
import type { ReasoningStep, Span, TerminologyConcept } from '../types';
import { ConceptSearch } from './ConceptSearch';

function randomId(prefix: string) {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

interface Props {
  steps: ReasoningStep[];
  availableSpans: Span[];
  onChange: (steps: ReasoningStep[]) => void;
}

export function ReasoningStepList({ steps, availableSpans, onChange }: Props) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftConcept, setDraftConcept] = useState<TerminologyConcept | null>(null);
  const [draftSpanIds, setDraftSpanIds] = useState<string[]>([]);

  const addStep = () => {
    const id = randomId('step');
    const newStep: ReasoningStep = {
      id,
      concept: { code: '', display: '', system: 'SNOMED-CT' },
      span_ids: [],
    };
    onChange([...steps, newStep]);
    setEditingId(id);
    setDraftConcept(null);
    setDraftSpanIds([]);
  };

  const commitEdit = (stepId: string) => {
    if (!draftConcept) return;
    onChange(
      steps.map((s) =>
        s.id === stepId ? { ...s, concept: draftConcept, span_ids: draftSpanIds } : s
      )
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

  return (
    <div className="item-list">
      {steps.map((step) => (
        <div
          key={step.id}
          className={`list-item${editingId === step.id ? ' editing' : ''}`}
        >
          {editingId === step.id ? (
            <div className="edit-form">
              <ConceptSearch
                value={draftConcept}
                onChange={setDraftConcept}
                placeholder="Search for intermediate concept..."
              />
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
            <div className="item-row">
              <div className="item-info">
                <span className="concept-label">
                  {step.concept.display || '(no concept)'}{' '}
                  {step.concept.code && (
                    <span className="concept-code">[{step.concept.code}]</span>
                  )}
                </span>
                <span className="item-meta">{step.span_ids.length} span(s) linked</span>
              </div>
              <div className="item-actions">
                <button
                  onClick={() => {
                    setEditingId(step.id);
                    setDraftConcept(step.concept.code ? step.concept : null);
                    setDraftSpanIds(step.span_ids);
                  }}
                  className="btn-small"
                >
                  Edit
                </button>
                <button onClick={() => deleteStep(step.id)} className="btn-small btn-danger">
                  Delete
                </button>
              </div>
            </div>
          )}
        </div>
      ))}
      <button onClick={addStep} className="btn-add">
        + Add Reasoning Step
      </button>
    </div>
  );
}
