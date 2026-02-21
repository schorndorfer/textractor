import { useEffect, useMemo, useState } from 'react';
import { api } from './api/client';
import { AnnotationPanel } from './components/AnnotationPanel';
import { DocumentList } from './components/DocumentList';
import { DocumentViewer } from './components/DocumentViewer';
import type { AnnotationFile, Document, DocumentSummary, Span } from './types';

// Color palette for document annotations (hue, saturation, lightness)
const COLOR_PALETTE = [
  { bg: '#e3f2fd', border: '#2196f3' }, // blue
  { bg: '#f3e5f5', border: '#9c27b0' }, // purple
  { bg: '#e8f5e9', border: '#4caf50' }, // green
  { bg: '#fff3e0', border: '#ff9800' }, // orange
  { bg: '#fce4ec', border: '#e91e63' }, // pink
  { bg: '#e0f7fa', border: '#00bcd4' }, // cyan
  { bg: '#fff9c4', border: '#fdd835' }, // yellow
  { bg: '#f1f8e9', border: '#8bc34a' }, // lime
  { bg: '#ede7f6', border: '#673ab7' }, // deep purple
  { bg: '#ffebee', border: '#f44336' }, // red
  { bg: '#e0f2f1', border: '#009688' }, // teal
  { bg: '#fff8e1', border: '#ffc107' }, // amber
];

export type SpanColorMap = Map<string, { bg: string; border: string }>;

export function App() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [currentDoc, setCurrentDoc] = useState<Document | null>(null);
  const [annotations, setAnnotations] = useState<AnnotationFile | null>(null);
  const [isDirty, setIsDirty] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedAnnotationId, setSelectedAnnotationId] = useState<string | null>(null);

  const refreshDocuments = () => {
    api.listDocuments().then(setDocuments).catch(console.error);
  };

  // Compute color mappings for document annotations, spans, and reasoning steps
  const { spanColorMap, docAnnColorMap, stepColorMap } = useMemo<{
    spanColorMap: SpanColorMap;
    docAnnColorMap: SpanColorMap;
    stepColorMap: SpanColorMap;
  }>(() => {
    const spanMap = new Map<string, { bg: string; border: string }>();
    const docAnnMap = new Map<string, { bg: string; border: string }>();
    const stepMap = new Map<string, { bg: string; border: string }>();
    if (!annotations) return { spanColorMap: spanMap, docAnnColorMap: docAnnMap, stepColorMap: stepMap };

    // Assign colors to document annotations
    annotations.document_annotations.forEach((ann, idx) => {
      docAnnMap.set(ann.id, COLOR_PALETTE[idx % COLOR_PALETTE.length]);
    });

    // Map spans and reasoning steps to colors via document annotations
    annotations.document_annotations.forEach((ann) => {
      const color = docAnnMap.get(ann.id);
      if (!color) return;

      // Direct evidence spans
      ann.evidence_span_ids.forEach((spanId) => {
        if (!spanMap.has(spanId)) {
          spanMap.set(spanId, color);
        }
      });

      // Reasoning steps
      ann.reasoning_step_ids.forEach((stepId) => {
        if (!stepMap.has(stepId)) {
          stepMap.set(stepId, color);
        }

        // Indirect spans via reasoning steps
        const step = annotations.reasoning_steps.find((s) => s.id === stepId);
        if (step) {
          step.span_ids.forEach((spanId) => {
            if (!spanMap.has(spanId)) {
              spanMap.set(spanId, color);
            }
          });
        }
      });
    });

    return { spanColorMap: spanMap, docAnnColorMap: docAnnMap, stepColorMap: stepMap };
  }, [annotations]);

  useEffect(() => {
    refreshDocuments();
  }, []);

  useEffect(() => {
    if (!selectedDocId) return;
    setLoading(true);
    setSelectedAnnotationId(null); // Clear selection when switching documents
    Promise.all([api.getDocument(selectedDocId), api.getAnnotations(selectedDocId)])
      .then(([doc, ann]) => {
        setCurrentDoc(doc);
        setAnnotations(ann);
        setIsDirty(false);
        setSaveError(null);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [selectedDocId]);

  const handleSpanCreated = (span: Span) => {
    if (!annotations) return;
    setAnnotations({ ...annotations, spans: [...annotations.spans, span] });
    setIsDirty(true);
  };

  const handleAnnotationChange = (updated: AnnotationFile) => {
    setAnnotations(updated);
    setIsDirty(true);
  };

  const handleSave = async () => {
    if (!annotations || !selectedDocId) return;
    setSaveError(null);
    try {
      await api.saveAnnotations(selectedDocId, annotations);
      setIsDirty(false);
      refreshDocuments();
    } catch (err) {
      setSaveError(String(err));
    }
  };

  const handleAnnotationSelect = (annotationId: string | null) => {
    console.log('handleAnnotationSelect called with:', annotationId);
    console.log('Previous selection:', selectedAnnotationId);
    setSelectedAnnotationId((prev) => {
      const newValue = prev === annotationId ? null : annotationId;
      console.log('New selection will be:', newValue);
      return newValue;
    });
  };

  // Compute visible spans based on selected annotation
  const visibleSpans = useMemo(() => {
    if (!annotations) return [];
    if (!selectedAnnotationId) return annotations.spans;

    const selectedAnn = annotations.document_annotations.find((a) => a.id === selectedAnnotationId);
    if (!selectedAnn) return annotations.spans;

    const visibleSpanIds = new Set<string>();

    // Add direct evidence spans
    selectedAnn.evidence_span_ids.forEach((id) => visibleSpanIds.add(id));

    // Add indirect spans via reasoning steps
    selectedAnn.reasoning_step_ids.forEach((stepId) => {
      const step = annotations.reasoning_steps.find((s) => s.id === stepId);
      if (step) {
        step.span_ids.forEach((spanId) => visibleSpanIds.add(spanId));
      }
    });

    return annotations.spans.filter((span) => visibleSpanIds.has(span.id));
  }, [annotations, selectedAnnotationId]);

  return (
    <div className="app-layout">
      <DocumentList
        documents={documents}
        selectedId={selectedDocId}
        onSelect={setSelectedDocId}
        onRefresh={refreshDocuments}
      />

      {loading && (
        <div className="loading-state">
          <span>Loading…</span>
        </div>
      )}

      {!loading && currentDoc && annotations ? (
        <>
          <DocumentViewer
            doc={currentDoc}
            spans={visibleSpans}
            spanColorMap={spanColorMap}
            onSpanCreated={handleSpanCreated}
          />
          <AnnotationPanel
            annotations={annotations}
            onChange={handleAnnotationChange}
            onSave={handleSave}
            isDirty={isDirty}
            saveError={saveError}
            spanColorMap={spanColorMap}
            docAnnColorMap={docAnnColorMap}
            stepColorMap={stepColorMap}
            selectedAnnotationId={selectedAnnotationId}
            onAnnotationSelect={handleAnnotationSelect}
          />
        </>
      ) : (
        !loading && (
          <div className="empty-state">
            <p>Select a document to begin annotating</p>
          </div>
        )
      )}
    </div>
  );
}

export default App;
