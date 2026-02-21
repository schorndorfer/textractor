import { useEffect, useState } from 'react';
import { api } from './api/client';
import { AnnotationPanel } from './components/AnnotationPanel';
import { DocumentList } from './components/DocumentList';
import { DocumentViewer } from './components/DocumentViewer';
import type { AnnotationFile, Document, DocumentSummary, Span } from './types';

export function App() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [currentDoc, setCurrentDoc] = useState<Document | null>(null);
  const [annotations, setAnnotations] = useState<AnnotationFile | null>(null);
  const [isDirty, setIsDirty] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const refreshDocuments = () => {
    api.listDocuments().then(setDocuments).catch(console.error);
  };

  useEffect(() => {
    refreshDocuments();
  }, []);

  useEffect(() => {
    if (!selectedDocId) return;
    setLoading(true);
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
            spans={annotations.spans}
            onSpanCreated={handleSpanCreated}
          />
          <AnnotationPanel
            annotations={annotations}
            onChange={handleAnnotationChange}
            onSave={handleSave}
            isDirty={isDirty}
            saveError={saveError}
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
