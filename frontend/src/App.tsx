import { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import { api } from './api/client';
import { AnnotationPanel } from './components/AnnotationPanel';
import { AnnotationGraph } from './components/AnnotationGraph';
import { DocumentList } from './components/DocumentList';
import { DocumentViewer } from './components/DocumentViewer';
import { ResizeHandle } from './components/ResizeHandle';
import type { AnnotationFile, Document, DocumentSummary, Span } from './types';
import { SIDEBAR, FONT_SIZE, AUTO_SAVE } from './constants';
import { deepClone } from './utils/helpers';
import { computeColorMappings } from './utils/colorMapping';
import type { ColorMap } from './utils/colorMapping';

export type SpanColorMap = ColorMap;

export function App() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [currentDoc, setCurrentDoc] = useState<Document | null>(null);
  const [annotations, setAnnotations] = useState<AnnotationFile | null>(null);
  const [originalAnnotations, setOriginalAnnotations] = useState<AnnotationFile | null>(null);
  const [isDirty, setIsDirty] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedAnnotationId, setSelectedAnnotationId] = useState<string | null>(null);
  const [focusedSpanId, setFocusedSpanId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'document' | 'graph'>('document');

  // Pre-annotation state
  const [isPreAnnotated, setIsPreAnnotated] = useState(false);
  const [preAnnotateLoading, setPreAnnotateLoading] = useState(false);
  const [preAnnotateError, setPreAnnotateError] = useState<string | null>(null);

  // Refs for auto-save
  const autoSaveTimeoutRef = useRef<number | null>(null);
  const isSavingRef = useRef(false);

  // Sidebar width and collapse state
  const [leftSidebarWidth, setLeftSidebarWidth] = useState(SIDEBAR.DEFAULT_LEFT_WIDTH);
  const [rightSidebarWidth, setRightSidebarWidth] = useState(SIDEBAR.DEFAULT_RIGHT_WIDTH);
  const [leftSidebarCollapsed, setLeftSidebarCollapsed] = useState(false);
  const [rightSidebarCollapsed, setRightSidebarCollapsed] = useState(false);

  // Font size state (persisted to localStorage)
  const [fontSize, setFontSize] = useState<number>(() => {
    const saved = localStorage.getItem(FONT_SIZE.STORAGE_KEY);
    return saved ? parseInt(saved, 10) : FONT_SIZE.DEFAULT;
  });

  const refreshDocuments = () => {
    api.listDocuments().then(setDocuments).catch(console.error);
  };

  // Compute color mappings for document annotations, spans, and reasoning steps
  const { spanColorMap, docAnnColorMap, stepColorMap } = useMemo(
    () => computeColorMappings(annotations),
    [annotations]
  );

  useEffect(() => {
    refreshDocuments();
  }, []);

  useEffect(() => {
    if (!selectedDocId) return;

    // Auto-save before switching documents
    const loadNewDocument = async () => {
      if (isDirty && annotations && !isSavingRef.current) {
        await saveAnnotations();
      }

      setLoading(true);
      setSelectedAnnotationId(null); // Clear selection when switching documents
      setFocusedSpanId(null); // Clear focused span when switching documents

      try {
        const [doc, ann] = await Promise.all([
          api.getDocument(selectedDocId),
          api.getAnnotations(selectedDocId)
        ]);
        setCurrentDoc(doc);
        setAnnotations(ann);
        setOriginalAnnotations(deepClone(ann));
        setIsDirty(false);
        setSaveError(null);
      } catch (error) {
        console.error(error);
      } finally {
        setLoading(false);
      }
    };

    loadNewDocument();
  }, [selectedDocId]);

  const handleSpanCreated = (span: Span) => {
    if (!annotations || annotations.completed) return; // Don't create spans in locked documents
    setAnnotations({ ...annotations, spans: [...annotations.spans, span] });
    setIsDirty(true);
  };

  const handleAnnotationChange = (updated: AnnotationFile) => {
    // Don't allow changes to locked documents (except toggling completed status)
    if (annotations?.completed && updated.completed) {
      return;
    }
    setAnnotations(updated);
    setIsDirty(true);
  };

  // Clear errors when document lock status changes
  useEffect(() => {
    if (annotations?.completed) {
      setSaveError(null);
    }
  }, [annotations?.completed]);

  // Debounced auto-save when annotations change
  useEffect(() => {
    if (!isDirty || !annotations || annotations.completed) return; // Don't auto-save locked documents

    // Clear existing timeout
    if (autoSaveTimeoutRef.current) {
      clearTimeout(autoSaveTimeoutRef.current);
    }

    // Set new timeout for auto-save
    autoSaveTimeoutRef.current = setTimeout(() => {
      saveAnnotations();
    }, AUTO_SAVE.DEBOUNCE_MS);

    return () => {
      if (autoSaveTimeoutRef.current) {
        clearTimeout(autoSaveTimeoutRef.current);
      }
    };
  }, [isDirty, annotations]);

  // Auto-save on page unload/refresh
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (isDirty && annotations && selectedDocId) {
        // Try to save
        saveAnnotations();
        // Note: Modern browsers ignore custom messages, but we still need to call preventDefault
        e.preventDefault();
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [isDirty, annotations, selectedDocId]);

  const saveAnnotations = async () => {
    if (!annotations || !selectedDocId || isSavingRef.current) return;

    // Allow saving when unlocking (completed changing from true to false)
    // Block saving when document is locked and not being unlocked
    const wasCompleted = originalAnnotations?.completed || false;
    const isCompleted = annotations.completed;
    const isUnlocking = wasCompleted && !isCompleted;

    if (isCompleted && !isUnlocking) {
      // Document is locked and we're not unlocking it, don't save
      return;
    }

    isSavingRef.current = true;
    setSaveError(null);
    try {
      await api.saveAnnotations(selectedDocId, annotations);
      setIsDirty(false);
      setOriginalAnnotations(deepClone(annotations));
      refreshDocuments();
    } catch (err) {
      // Suppress 403 errors for locked documents
      const errorStr = String(err);
      if (!errorStr.includes('403')) {
        setSaveError(errorStr);
      }
    } finally {
      isSavingRef.current = false;
    }
  };

  const handleRevert = () => {
    if (originalAnnotations) {
      setAnnotations(deepClone(originalAnnotations));
      setIsDirty(false);
      setSaveError(null);
    }
  };

  const handleAnnotationSelect = (annotationId: string | null) => {
    setSelectedAnnotationId((prev) => {
      const newValue = prev === annotationId ? null : annotationId;
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
      return Math.max(SIDEBAR.MIN_WIDTH, Math.min(SIDEBAR.MAX_WIDTH, newWidth));
    });
  }, []);

  const handleRightResize = useCallback((delta: number) => {
    setRightSidebarWidth((prev) => {
      const newWidth = prev + delta;
      return Math.max(SIDEBAR.MIN_WIDTH, Math.min(SIDEBAR.MAX_WIDTH, newWidth));
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
      const newSize = Math.max(FONT_SIZE.MIN, Math.min(FONT_SIZE.MAX, prev + delta));
      localStorage.setItem(FONT_SIZE.STORAGE_KEY, newSize.toString());
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
                disabled={annotations?.completed || false}
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
                onRevert={handleRevert}
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
