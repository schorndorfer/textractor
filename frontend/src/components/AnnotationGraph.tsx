import { useEffect, useRef } from 'react';
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
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
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

  // Collect all spans (from both direct evidence and reasoning steps)
  const allSpanIds = new Set<string>();
  directSpans.forEach((span) => allSpanIds.add(span.id));
  relatedSteps.forEach((step) => {
    step.span_ids.forEach((spanId) => allSpanIds.add(spanId));
  });
  const allSpans = annotations.spans.filter((span) => allSpanIds.has(span.id));

  // Draw edges between nodes
  useEffect(() => {
    if (!containerRef.current || !svgRef.current) return;

    const svg = svgRef.current;
    const container = containerRef.current;

    // Clear existing paths
    const existingPaths = svg.querySelectorAll('path.edge-path');
    existingPaths.forEach((path) => path.remove());

    // Get container offset
    const containerRect = container.getBoundingClientRect();

    // Function to get node center position
    const getNodeCenter = (nodeId: string) => {
      const node = container.querySelector(`#node-${nodeId}`) as HTMLElement;
      if (!node) return null;
      const rect = node.getBoundingClientRect();
      return {
        x: rect.left + rect.width / 2 - containerRect.left,
        y: rect.top + rect.height / 2 - containerRect.top,
      };
    };

    // Draw edges from Document Annotation to Reasoning Steps
    relatedSteps.forEach((step) => {
      const from = getNodeCenter(selectedAnn.id);
      const to = getNodeCenter(step.id);
      if (from && to) {
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('class', 'edge-path');
        path.setAttribute('d', `M ${from.x} ${from.y} L ${to.x} ${to.y}`);
        path.setAttribute('stroke', '#999');
        path.setAttribute('stroke-width', '2');
        path.setAttribute('stroke-dasharray', '4');
        path.setAttribute('fill', 'none');
        path.setAttribute('marker-end', 'url(#arrowhead)');
        svg.appendChild(path);
      }
    });

    // Draw edges from Document Annotation to Direct Evidence Spans
    directSpans.forEach((span) => {
      const from = getNodeCenter(selectedAnn.id);
      const to = getNodeCenter(span.id);
      if (from && to) {
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('class', 'edge-path');
        path.setAttribute('d', `M ${from.x} ${from.y} L ${to.x} ${to.y}`);
        path.setAttribute('stroke', '#999');
        path.setAttribute('stroke-width', '2');
        path.setAttribute('stroke-dasharray', '4');
        path.setAttribute('fill', 'none');
        path.setAttribute('marker-end', 'url(#arrowhead)');
        svg.appendChild(path);
      }
    });

    // Draw edges from Reasoning Steps to their Spans
    relatedSteps.forEach((step) => {
      step.span_ids.forEach((spanId) => {
        const from = getNodeCenter(step.id);
        const to = getNodeCenter(spanId);
        if (from && to) {
          const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
          path.setAttribute('class', 'edge-path');
          path.setAttribute('d', `M ${from.x} ${from.y} L ${to.x} ${to.y}`);
          path.setAttribute('stroke', '#999');
          path.setAttribute('stroke-width', '2');
          path.setAttribute('stroke-dasharray', '4');
          path.setAttribute('fill', 'none');
          path.setAttribute('marker-end', 'url(#arrowhead)');
          svg.appendChild(path);
        }
      });
    });
  }, [selectedAnnotationId, relatedSteps, directSpans, selectedAnn.id]);

  return (
    <div className="annotation-graph" ref={containerRef}>
      <div className="graph-container-dag">
        {/* Document Annotation (Top) */}
        <div className="graph-level">
          <h3 className="graph-level-title">Document Annotation</h3>
          <div className="graph-nodes">
            <div
              id={`node-${selectedAnn.id}`}
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

        {/* SVG for edges */}
        <svg ref={svgRef} className="graph-edges" style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 0 }}>
          <defs>
            <marker
              id="arrowhead"
              markerWidth="10"
              markerHeight="10"
              refX="9"
              refY="3"
              orient="auto"
            >
              <polygon points="0 0, 10 3, 0 6" fill="#999" />
            </marker>
          </defs>
        </svg>

        {/* Reasoning Steps (Middle) */}
        {relatedSteps.length > 0 && (
          <div className="graph-level">
            <h3 className="graph-level-title">Reasoning Steps ({relatedSteps.length})</h3>
            <div className="graph-nodes">
              {relatedSteps.map((step) => {
                const stepColor = stepColorMap.get(step.id);
                return (
                  <div key={step.id} className="graph-node-wrapper">
                    <div
                      id={`node-${step.id}`}
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
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Evidence Spans (Bottom) */}
        {allSpans.length > 0 && (
          <div className="graph-level">
            <h3 className="graph-level-title">Evidence Spans ({allSpans.length})</h3>
            <div className="graph-nodes graph-nodes-spans">
              {allSpans.map((span) => {
                const spanColor = spanColorMap.get(span.id);
                return (
                  <div key={span.id} className="graph-node-wrapper">
                    <div
                      id={`node-${span.id}`}
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
