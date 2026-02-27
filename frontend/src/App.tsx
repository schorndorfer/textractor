import { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import { api, ApiError } from './api/client';
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
  const [preAnnotateLoading, setPreAnnotateLoading] = useState(false);
  const [preAnnotateError, setPreAnnotateError] = useState<string | null>(null);

  // Refs for auto-save
  const autoSaveTimeoutRef = useRef<number | null>(null);
  const isSavingRef = useRef(false);
  const prevSelectedDocIdRef = useRef<string | null>(null);

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

  const refreshDocuments = useCallback(() => {
    api.listDocuments().then(setDocuments).catch(console.error);
  }, []);

  const saveAnnotations = useCallback(async () => {
    if (!annotations || !selectedDocId || isSavingRef.current) return;

    // Allow saving when lock state changes (locking or unlocking)
    // Block saving when document is already locked and lock state is unchanged
    const wasCompleted = originalAnnotations?.completed || false;
    const isCompleted = annotations.completed || false;
    const lockStateChanged = wasCompleted !== isCompleted;

    if (isCompleted && !lockStateChanged) {
      // Document is locked and we're not unlocking it, don't save
      return;
    }

    isSavingRef.current = true;
    setSaveError(null);
    try {
      // Use annotations.doc_id (source of truth) instead of selectedDocId
      // to avoid doc_id mismatch during document switching
      await api.saveAnnotations(annotations.doc_id, annotations);
      setIsDirty(false);
      setOriginalAnnotations(deepClone(annotations));
      refreshDocuments();
    } catch (err) {
      // Suppress 403 errors for locked documents
      if (err instanceof ApiError && err.status === 403) {
        return;
      }

      const errorStr = String(err);
      if (!errorStr.includes('403')) {
        setSaveError(errorStr);
      }
    } finally {
      isSavingRef.current = false;
    }
  }, [annotations, selectedDocId, originalAnnotations, refreshDocuments]);

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

    // Only load if selectedDocId actually changed
    if (prevSelectedDocIdRef.current === selectedDocId) return;
    prevSelectedDocIdRef.current = selectedDocId;

    // Auto-save before switching documents
    const loadNewDocument = async () => {
      if (isDirty && annotations && !isSavingRef.current) {
        await saveAnnotations();
      }

      setLoading(true);
      setSelectedAnnotationId(null); // Clear selection when switching documents
      setFocusedSpanId(null); // Clear focused span when switching documents
      setPreAnnotateError(null); // Clear pre-annotate errors

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
  }, [selectedDocId, isDirty, annotations, saveAnnotations]);

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

  const handleToggleCompleted = () => {
    if (!annotations) return;
    handleAnnotationChange({ ...annotations, completed: !annotations.completed });
  };

  // Clear errors when document lock status changes
  useEffect(() => {
    if (annotations?.completed) {
      setSaveError(null);
    }
  }, [annotations?.completed]);

  // Debounced auto-save when annotations change
  useEffect(() => {
    if (!isDirty || !annotations) return;

    const wasCompleted = originalAnnotations?.completed || false;
    const isCompleted = annotations.completed || false;
    const lockStateChanged = wasCompleted !== isCompleted;

    // Don't auto-save locked documents unless lock state changed
    if (isCompleted && !lockStateChanged) return;

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
  }, [isDirty, annotations, originalAnnotations, saveAnnotations]);

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
  }, [isDirty, annotations, selectedDocId, saveAnnotations]);

  const handleRevert = () => {
    if (originalAnnotations) {
      setAnnotations(deepClone(originalAnnotations));
      setIsDirty(false);
      setSaveError(null);
      setPreAnnotateError(null); // Clear pre-annotate errors
    }
  };

  const handlePreAnnotate = async () => {
    if (!selectedDocId) return;

    setPreAnnotateLoading(true);
    setPreAnnotateError(null);

    try {
      const aiAnnotations = await api.preannotateDocument(selectedDocId);

      // Load AI annotations and mark as dirty to trigger auto-save
      setAnnotations(aiAnnotations);
      setOriginalAnnotations(deepClone(aiAnnotations)); // Update baseline to prevent revert
      setIsDirty(false); // Not dirty since we just loaded fresh AI content

      // Explicitly save the AI-generated annotations immediately
      await api.saveAnnotations(aiAnnotations.doc_id, aiAnnotations);
      refreshDocuments();

    } catch (err) {
      let errorMsg = 'Pre-annotation failed';
      const status = err instanceof ApiError ? err.status : null;
      const detail = err instanceof ApiError ? err.detail : String(err);

      if (status === 500 && detail.includes('ANTHROPIC_API_KEY')) {
        errorMsg = 'API key not configured. Please contact administrator.';
      } else if (
        (status === 500 || status === 502) &&
        (detail.includes('TEXTRACTOR_LLM_MODEL') ||
          detail.includes('AWS Bedrock') ||
          detail.includes('direct Anthropic API') ||
          detail.includes('configured provider'))
      ) {
        errorMsg =
          'LLM model/provider configuration error. Check TEXTRACTOR_LLM_MODEL for your auth mode (Bedrock vs direct Anthropic).';
      } else if (status === 502) {
        errorMsg = 'AI service error. Please try again.';
      } else if (status === 403) {
        errorMsg = 'Cannot pre-annotate a locked document.';
      }

      setPreAnnotateError(errorMsg);
    } finally {
      setPreAnnotateLoading(false);
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
              selectedDocCompleted={annotations?.completed || false}
              onToggleSelectedCompleted={handleToggleCompleted}
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
                onPreAnnotate={handlePreAnnotate}
                isPreAnnotating={preAnnotateLoading}
                preAnnotateError={preAnnotateError}
              />
            </>
          )
        )}
      </div>
    </div>
  );
}

export default App;
