import type { AnnotationFile } from '../types';
import type { SpanColorMap } from '../App';

interface Props {
  selectedAnnotationId: string | null;
  annotations: AnnotationFile;
  spanColorMap: SpanColorMap;
  docAnnColorMap: SpanColorMap;
  stepColorMap: SpanColorMap;
}

export function AnnotationGraph({
  selectedAnnotationId,
  annotations,
  spanColorMap,
  docAnnColorMap,
  stepColorMap,
}: Props) {
  if (!selectedAnnotationId) {
    return (
      <div className="graph-empty-state">
        <p>Select a document annotation to view its evidence graph</p>
      </div>
    );
  }

  const selectedAnn = annotations.document_annotations.find((a) => a.id === selectedAnnotationId);
  if (!selectedAnn) {
    return (
      <div className="graph-empty-state">
        <p>Annotation not found</p>
      </div>
    );
  }

  const color = docAnnColorMap.get(selectedAnn.id);

  // Get related reasoning steps
  const relatedSteps = annotations.reasoning_steps.filter((step) =>
    selectedAnn.reasoning_step_ids.includes(step.id)
  );

  // Get direct evidence spans
  const directSpans = annotations.spans.filter((span) =>
    selectedAnn.evidence_span_ids.includes(span.id)
  );

  // Get indirect spans through reasoning steps
  const indirectSpanIds = new Set<string>();
  relatedSteps.forEach((step) => {
    step.span_ids.forEach((spanId) => indirectSpanIds.add(spanId));
  });
  const indirectSpans = annotations.spans.filter((span) => indirectSpanIds.has(span.id));

  return (
    <div className="annotation-graph">
      <div className="graph-container">
        {/* Document Annotation (Top) */}
        <div className="graph-level">
          <h3 className="graph-level-title">Document Annotation</h3>
          <div className="graph-nodes">
            <div
              className="graph-node graph-node-annotation"
              style={{
                borderColor: color?.border,
                backgroundColor: color?.bg,
              }}
            >
              <div className="node-label">{selectedAnn.concept.display}</div>
              <div className="node-code">{selectedAnn.concept.code}</div>
            </div>
          </div>
        </div>

        {/* Connectors to Reasoning Steps */}
        {relatedSteps.length > 0 && (
          <>
            <div className="graph-connector-line" />
            {/* Reasoning Steps (Middle) */}
            <div className="graph-level">
              <h3 className="graph-level-title">Reasoning Steps ({relatedSteps.length})</h3>
              <div className="graph-nodes">
                {relatedSteps.map((step) => {
                  const stepColor = stepColorMap.get(step.id);
                  return (
                    <div key={step.id} className="graph-node-container">
                      <div
                        className="graph-node graph-node-step"
                        style={{
                          borderColor: stepColor?.border,
                          backgroundColor: stepColor?.bg,
                        }}
                      >
                        <div className="node-label">{step.concept.display}</div>
                        <div className="node-code">{step.concept.code}</div>
                        {step.span_ids.length > 0 && (
                          <div className="node-meta">{step.span_ids.length} span(s)</div>
                        )}
                      </div>
                      {/* Connectors to spans for this step */}
                      {step.span_ids.length > 0 && <div className="graph-connector-branch" />}
                    </div>
                  );
                })}
              </div>
            </div>
          </>
        )}

        {/* Direct Evidence Spans */}
        {directSpans.length > 0 && (
          <>
            {relatedSteps.length === 0 && <div className="graph-connector-line" />}
            <div className="graph-level">
              <h3 className="graph-level-title">Direct Evidence ({directSpans.length})</h3>
              <div className="graph-nodes graph-nodes-spans">
                {directSpans.map((span) => {
                  const spanColor = spanColorMap.get(span.id);
                  return (
                    <div
                      key={span.id}
                      className="graph-node graph-node-span"
                      style={{
                        borderColor: spanColor?.border,
                        backgroundColor: spanColor?.bg,
                      }}
                    >
                      <div className="node-text">{span.text}</div>
                      <div className="node-offsets">
                        [{span.start}–{span.end}]
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </>
        )}

        {/* Indirect Evidence Spans (through reasoning steps) */}
        {indirectSpans.length > 0 && (
          <div className="graph-level">
            <h3 className="graph-level-title">Indirect Evidence ({indirectSpans.length})</h3>
            <div className="graph-nodes graph-nodes-spans">
              {indirectSpans.map((span) => {
                const spanColor = spanColorMap.get(span.id);
                return (
                  <div
                    key={span.id}
                    className="graph-node graph-node-span"
                    style={{
                      borderColor: spanColor?.border,
                      backgroundColor: spanColor?.bg,
                    }}
                  >
                    <div className="node-text">{span.text}</div>
                    <div className="node-offsets">
                      [{span.start}–{span.end}]
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
