import { useMemo, useEffect } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MarkerType,
  useNodesState,
  useEdgesState,
} from 'reactflow';
import type { Node, Edge } from 'reactflow';
import 'reactflow/dist/style.css';
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
  // Compute initial nodes and edges
  const { initialNodes, initialEdges } = useMemo(() => {
    if (!selectedAnnotationId) {
      return { initialNodes: [], initialEdges: [] };
    }

    const selectedAnn = annotations.document_annotations.find((a) => a.id === selectedAnnotationId);
    if (!selectedAnn) {
      return { initialNodes: [], initialEdges: [] };
    }

    const color = docAnnColorMap.get(selectedAnn.id);
    const nodes: Node[] = [];
    const edges: Edge[] = [];

    // Get related reasoning steps
    const relatedSteps = annotations.reasoning_steps.filter((step) =>
      selectedAnn.reasoning_step_ids.includes(step.id)
    );

    // Get direct evidence spans
    const directSpans = annotations.spans.filter((span) =>
      selectedAnn.evidence_span_ids.includes(span.id)
    );

    // Collect all spans
    const allSpanIds = new Set<string>();
    directSpans.forEach((span) => allSpanIds.add(span.id));
    relatedSteps.forEach((step) => {
      step.span_ids.forEach((spanId) => allSpanIds.add(spanId));
    });
    const allSpans = annotations.spans.filter((span) => allSpanIds.has(span.id));

    // Add Document Annotation node
    nodes.push({
      id: selectedAnn.id,
      type: 'default',
      position: { x: 400, y: 50 },
      data: {
        label: (
          <div
            className="graph-node graph-node-annotation"
            style={{
              borderColor: color?.border,
              backgroundColor: color?.bg,
            }}
          >
            <div className="node-label">
              {selectedAnn.source === 'model' && (
                <span className="ai-badge" title="Model-generated">⚙</span>
              )}
              {selectedAnn.concept.display}
            </div>
            <div className="node-code">{selectedAnn.concept.code}</div>
          </div>
        ),
      },
      style: {
        background: 'transparent',
        border: 'none',
        padding: 0,
      },
    });

    // Add Reasoning Step nodes
    const stepSpacing = 250;
    const stepStartX = relatedSteps.length > 1
      ? 400 - ((relatedSteps.length - 1) * stepSpacing) / 2
      : 400;

    relatedSteps.forEach((step, idx) => {
      const stepColor = stepColorMap.get(step.id);
      nodes.push({
        id: step.id,
        type: 'default',
        position: { x: stepStartX + idx * stepSpacing, y: 250 },
        data: {
          label: (
            <div
              className="graph-node graph-node-step"
              style={{
                borderColor: stepColor?.border,
                backgroundColor: stepColor?.bg,
              }}
            >
              <div className="node-label">
                {step.source === 'model' && (
                  <span className="ai-badge" title="Model-generated">⚙</span>
                )}
                {step.concept.display}
              </div>
              <div className="node-code">{step.concept.code}</div>
              {step.span_ids.length > 0 && (
                <div className="node-meta">{step.span_ids.length} span(s)</div>
              )}
            </div>
          ),
        },
        style: {
          background: 'transparent',
          border: 'none',
          padding: 0,
        },
      });

      // Edge from Document Annotation to Reasoning Step
      edges.push({
        id: `edge-${selectedAnn.id}-${step.id}`,
        source: selectedAnn.id,
        target: step.id,
        type: 'default',
        animated: false,
        style: { stroke: '#999', strokeWidth: 2, strokeDasharray: '5,5' },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#999' },
      });
    });

    // Add Span nodes
    const spanSpacing = 220;
    const spanStartX = allSpans.length > 1
      ? 400 - ((allSpans.length - 1) * spanSpacing) / 2
      : 400;

    allSpans.forEach((span, idx) => {
      const spanColor = spanColorMap.get(span.id);
      nodes.push({
        id: span.id,
        type: 'default',
        position: { x: spanStartX + idx * spanSpacing, y: 450 },
        data: {
          label: (
            <div
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
          ),
        },
        style: {
          background: 'transparent',
          border: 'none',
          padding: 0,
        },
      });
    });

    // Edges from Document Annotation to Direct Evidence Spans
    directSpans.forEach((span) => {
      edges.push({
        id: `edge-${selectedAnn.id}-${span.id}`,
        source: selectedAnn.id,
        target: span.id,
        type: 'default',
        animated: false,
        style: { stroke: '#999', strokeWidth: 2, strokeDasharray: '5,5' },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#999' },
      });
    });

    // Edges from Reasoning Steps to their Spans
    relatedSteps.forEach((step) => {
      step.span_ids.forEach((spanId) => {
        edges.push({
          id: `edge-${step.id}-${spanId}`,
          source: step.id,
          target: spanId,
          type: 'default',
          animated: false,
          style: { stroke: '#999', strokeWidth: 2, strokeDasharray: '5,5' },
          markerEnd: { type: MarkerType.ArrowClosed, color: '#999' },
        });
      });
    });

    return { initialNodes: nodes, initialEdges: edges };
  }, [selectedAnnotationId, annotations, spanColorMap, docAnnColorMap, stepColorMap]);

  // Use React Flow state hooks to enable dragging
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Update nodes and edges when annotation changes
  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [initialNodes, initialEdges, setNodes, setEdges]);

  if (!selectedAnnotationId) {
    return (
      <div className="graph-empty-state">
        <p>Select a document annotation to view its evidence graph</p>
      </div>
    );
  }

  if (nodes.length === 0) {
    return (
      <div className="graph-empty-state">
        <p>Annotation not found</p>
      </div>
    );
  }

  return (
    <div className="annotation-graph-flow">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        nodesDraggable={true}
        nodesConnectable={false}
        elementsSelectable={true}
        zoomOnScroll={true}
        panOnDrag={true}
        proOptions={{ hideAttribution: true }}
      >
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}
