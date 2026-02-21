import { useState, useEffect, useRef } from 'react';
import { api } from '../api/client';
import type { DocumentSummary } from '../types';

type Filter = 'all' | 'annotated' | 'unannotated';

interface Props {
  documents: DocumentSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onRefresh: () => void;
  onToggleCollapse?: () => void;
  collapsed?: boolean;
}

export function DocumentList({ documents, selectedId, onSelect, onRefresh, onToggleCollapse, collapsed }: Props) {
  const [filter, setFilter] = useState<Filter>('all');
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [showUploadMenu, setShowUploadMenu] = useState(false);
  const uploadMenuRef = useRef<HTMLDivElement>(null);

  const filtered = documents.filter((d) => {
    if (filter === 'annotated') return d.is_annotated;
    if (filter === 'unannotated') return !d.is_annotated;
    return true;
  });

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (uploadMenuRef.current && !uploadMenuRef.current.contains(event.target as Node)) {
        setShowUploadMenu(false);
      }
    };

    if (showUploadMenu) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [showUploadMenu]);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = e.target.files;
    if (!fileList || fileList.length === 0) return;

    const files = Array.from(fileList).filter((f) => f.name.endsWith('.json'));
    if (files.length === 0) {
      setUploadError('No valid .json files selected');
      return;
    }

    setUploading(true);
    setUploadError(null);
    try {
      const results = await api.uploadDocuments(files);
      const skipped = files.length - results.length;
      if (skipped > 0) {
        setUploadError(`Uploaded ${results.length} file(s). ${skipped} skipped (duplicates or errors).`);
      }
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
        <div className="upload-container" ref={uploadMenuRef}>
          <button
            className={`upload-btn${uploading ? ' uploading' : ''}`}
            onClick={() => setShowUploadMenu(!showUploadMenu)}
            disabled={uploading}
          >
            {uploading ? '...' : 'Upload ▾'}
          </button>
          {showUploadMenu && (
            <div className="upload-menu">
              <label className="upload-menu-item">
                Files
                <input
                  type="file"
                  accept=".json"
                  onChange={(e) => {
                    handleFileUpload(e);
                    setShowUploadMenu(false);
                  }}
                  multiple
                  hidden
                />
              </label>
              <label className="upload-menu-item">
                Folder
                <input
                  type="file"
                  accept=".json"
                  onChange={(e) => {
                    handleFileUpload(e);
                    setShowUploadMenu(false);
                  }}
                  {...({ webkitdirectory: '', directory: '' } as any)}
                  hidden
                />
              </label>
            </div>
          )}
        </div>
        {onToggleCollapse && (
          <button
            className="sidebar-toggle"
            onClick={onToggleCollapse}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            ‹
          </button>
        )}
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
            {doc.metadata.category != null && (
              <div className="doc-category">{String(doc.metadata.category)}</div>
            )}
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
