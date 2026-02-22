import { useEffect, useMemo, useState, useCallback } from 'react';
import { api } from './api/client';
import { AnnotationPanel } from './components/AnnotationPanel';
import { AnnotationGraph } from './components/AnnotationGraph';
import { DocumentList } from './components/DocumentList';
import { DocumentViewer } from './components/DocumentViewer';
import { ResizeHandle } from './components/ResizeHandle';
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

const MIN_SIDEBAR_WIDTH = 200;
const MAX_SIDEBAR_WIDTH = 600;
const DEFAULT_LEFT_WIDTH = 260;
const DEFAULT_RIGHT_WIDTH = 380;
const DEFAULT_FONT_SIZE = 14;

export function App() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [currentDoc, setCurrentDoc] = useState<Document | null>(null);
  const [annotations, setAnnotations] = useState<AnnotationFile | null>(null);
  const [isDirty, setIsDirty] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedAnnotationId, setSelectedAnnotationId] = useState<string | null>(null);
  const [focusedSpanId, setFocusedSpanId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'document' | 'graph'>('document');

  // Sidebar width and collapse state
  const [leftSidebarWidth, setLeftSidebarWidth] = useState(DEFAULT_LEFT_WIDTH);
  const [rightSidebarWidth, setRightSidebarWidth] = useState(DEFAULT_RIGHT_WIDTH);
  const [leftSidebarCollapsed, setLeftSidebarCollapsed] = useState(false);
  const [rightSidebarCollapsed, setRightSidebarCollapsed] = useState(false);

  // Font size state (persisted to localStorage)
  const [fontSize, setFontSize] = useState<number>(() => {
    const saved = localStorage.getItem('textractor-font-size');
    return saved ? parseInt(saved, 10) : DEFAULT_FONT_SIZE;
  });

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
    setFocusedSpanId(null); // Clear focused span when switching documents
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
      // Auto-switch to graph tab when annotation is selected
      if (newValue !== null) {
        setActiveTab('graph');
      } else {
        // Switch back to document tab when annotation is deselected
        setActiveTab('document');
      }
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

  // Resize handlers
  const handleLeftResize = useCallback((delta: number) => {
    setLeftSidebarWidth((prev) => {
      const newWidth = prev + delta;
      return Math.max(MIN_SIDEBAR_WIDTH, Math.min(MAX_SIDEBAR_WIDTH, newWidth));
    });
  }, []);

  const handleRightResize = useCallback((delta: number) => {
    setRightSidebarWidth((prev) => {
      const newWidth = prev + delta;
      return Math.max(MIN_SIDEBAR_WIDTH, Math.min(MAX_SIDEBAR_WIDTH, newWidth));
    });
  }, []);

  // Collapse/expand handlers
  const toggleLeftSidebar = useCallback(() => {
    setLeftSidebarCollapsed((prev) => !prev);
  }, []);

  const toggleRightSidebar = useCallback(() => {
    setRightSidebarCollapsed((prev) => !prev);
  }, []);

  // Font size handlers
  const handleFontSizeChange = useCallback((delta: number) => {
    setFontSize((prev) => {
      const newSize = Math.max(10, Math.min(24, prev + delta));
      localStorage.setItem('textractor-font-size', newSize.toString());
      return newSize;
    });
  }, []);

  return (
    <div
      className="app-layout"
      style={{
        gridTemplateColumns: `${leftSidebarCollapsed ? 40 : leftSidebarWidth}px 1fr ${rightSidebarCollapsed ? 40 : rightSidebarWidth}px`,
      }}
    >
      {/* Left Sidebar (Document List) */}
      <div className={`sidebar-container sidebar-left${leftSidebarCollapsed ? ' collapsed' : ''}`}>
        {leftSidebarCollapsed ? (
          <button
            className="sidebar-toggle"
            onClick={toggleLeftSidebar}
            title="Expand sidebar"
          >
            ›
          </button>
        ) : (
          <>
            <DocumentList
              documents={documents}
              selectedId={selectedDocId}
              onSelect={setSelectedDocId}
              onRefresh={refreshDocuments}
              onToggleCollapse={toggleLeftSidebar}
              collapsed={leftSidebarCollapsed}
            />
            <ResizeHandle onResize={handleLeftResize} direction="left" />
          </>
        )}
      </div>

      {/* Main Content Area */}
      {loading && (
        <div className="loading-state">
          <span>Loading…</span>
        </div>
      )}

      {!loading && currentDoc && annotations ? (
        <div className="main-content">
          {/* Tab Navigation */}
          <div className="tab-navigation">
            <button
              className={`tab-button${activeTab === 'document' ? ' active' : ''}`}
              onClick={() => setActiveTab('document')}
            >
              Document Text
            </button>
            <button
              className={`tab-button${activeTab === 'graph' ? ' active' : ''}`}
              onClick={() => setActiveTab('graph')}
              disabled={!selectedAnnotationId}
              title={!selectedAnnotationId ? 'Select an annotation to view graph' : 'View annotation graph'}
            >
              Annotation Graph
            </button>
          </div>

          {/* Tab Content */}
          <div className="tab-content">
            {activeTab === 'document' ? (
              <DocumentViewer
                doc={currentDoc}
                spans={visibleSpans}
                spanColorMap={spanColorMap}
                onSpanCreated={handleSpanCreated}
                fontSize={fontSize}
                onFontSizeChange={handleFontSizeChange}
                focusedSpanId={focusedSpanId}
              />
            ) : (
              <AnnotationGraph
                selectedAnnotationId={selectedAnnotationId}
                annotations={annotations}
                spanColorMap={spanColorMap}
                docAnnColorMap={docAnnColorMap}
                stepColorMap={stepColorMap}
              />
            )}
          </div>
        </div>
      ) : (
        !loading && (
          <div className="empty-state">
            <p>Select a document to begin annotating</p>
          </div>
        )
      )}

      {/* Right Sidebar (Annotation Panel) */}
      <div className={`sidebar-container sidebar-right${rightSidebarCollapsed ? ' collapsed' : ''}`}>
        {rightSidebarCollapsed ? (
          <button
            className="sidebar-toggle"
            onClick={toggleRightSidebar}
            title="Expand sidebar"
          >
            ‹
          </button>
        ) : (
          currentDoc && annotations && (
            <>
              <ResizeHandle onResize={handleRightResize} direction="right" />
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
                onToggleCollapse={toggleRightSidebar}
                collapsed={rightSidebarCollapsed}
                onSpanClick={setFocusedSpanId}
              />
            </>
          )
        )}
      </div>
    </div>
  );
}

export default App;
