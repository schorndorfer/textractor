import { useState } from 'react';
import { api } from '../api/client';
import type { DocumentSummary } from '../types';

type Filter = 'all' | 'annotated' | 'unannotated';

interface Props {
  documents: DocumentSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onRefresh: () => void;
}

export function DocumentList({ documents, selectedId, onSelect, onRefresh }: Props) {
  const [filter, setFilter] = useState<Filter>('all');
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const filtered = documents.filter((d) => {
    if (filter === 'annotated') return d.is_annotated;
    if (filter === 'unannotated') return !d.is_annotated;
    return true;
  });

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    try {
      await api.uploadDocument(file);
      onRefresh();
    } catch (err) {
      setUploadError(String(err));
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  return (
    <aside className="doc-list">
      <div className="doc-list-header">
        <h2>Documents</h2>
        <label className={`upload-btn${uploading ? ' uploading' : ''}`}>
          {uploading ? '...' : 'Upload'}
          <input type="file" accept=".json" onChange={handleFileUpload} hidden />
        </label>
      </div>
      {uploadError && <p className="upload-error">{uploadError}</p>}
      <div className="filter-tabs">
        {(['all', 'annotated', 'unannotated'] as Filter[]).map((f) => (
          <button
            key={f}
            className={`filter-tab${filter === f ? ' active' : ''}`}
            onClick={() => setFilter(f)}
          >
            {f}
          </button>
        ))}
      </div>
      <ul className="doc-items">
        {filtered.map((doc) => (
          <li
            key={doc.id}
            className={`doc-item${doc.id === selectedId ? ' selected' : ''}${doc.is_annotated ? ' annotated' : ''}`}
            onClick={() => onSelect(doc.id)}
          >
            <div className="doc-item-header">
              <span className="doc-item-id">{doc.id}</span>
              {doc.is_annotated && <span className="badge">✓</span>}
            </div>
            <p className="doc-preview">{doc.text_preview}</p>
          </li>
        ))}
        {filtered.length === 0 && (
          <li className="empty-hint">
            {documents.length === 0
              ? 'Upload a document JSON file to get started'
              : 'No documents match filter'}
          </li>
        )}
      </ul>
    </aside>
  );
}
