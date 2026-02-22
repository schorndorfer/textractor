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
  const [expandedProjects, setExpandedProjects] = useState<Set<string>>(new Set(['Uncategorized']));
  const [editingProject, setEditingProject] = useState<string | null>(null);
  const [newProjectName, setNewProjectName] = useState('');
  const [showProjectMenu, setShowProjectMenu] = useState<string | null>(null);
  const uploadMenuRef = useRef<HTMLDivElement>(null);
  const projectMenuRef = useRef<HTMLDivElement>(null);

  const filtered = documents.filter((d) => {
    if (filter === 'annotated') return d.is_annotated;
    if (filter === 'unannotated') return !d.is_annotated;
    return true;
  });

  // Group documents by project
  const projectGroups = new Map<string, DocumentSummary[]>();
  filtered.forEach((doc) => {
    const project = doc.metadata.project ? String(doc.metadata.project) : 'Uncategorized';
    if (!projectGroups.has(project)) {
      projectGroups.set(project, []);
    }
    projectGroups.get(project)!.push(doc);
  });

  const toggleProject = (project: string) => {
    setExpandedProjects((prev) => {
      const next = new Set(prev);
      if (next.has(project)) {
        next.delete(project);
      } else {
        next.add(project);
      }
      return next;
    });
  };

  const handleRenameProject = async (oldName: string, newName: string) => {
    if (!newName.trim() || newName === oldName) {
      setEditingProject(null);
      return;
    }

    const docsInProject = projectGroups.get(oldName) || [];
    try {
      for (const doc of docsInProject) {
        await api.updateDocumentMetadata(doc.id, { project: newName });
      }
      setEditingProject(null);
      onRefresh();
    } catch (err) {
      setUploadError(`Failed to rename project: ${err}`);
    }
  };

  const handleDeleteProject = async (projectName: string) => {
    if (projectName === 'Uncategorized') {
      setUploadError('Cannot delete the Uncategorized project');
      return;
    }

    if (!confirm(`Delete project "${projectName}"? Documents will be moved to Uncategorized.`)) {
      return;
    }

    const docsInProject = projectGroups.get(projectName) || [];
    try {
      for (const doc of docsInProject) {
        const updatedMetadata = { ...doc.metadata };
        delete updatedMetadata.project;
        await api.updateDocumentMetadata(doc.id, updatedMetadata);
      }
      setShowProjectMenu(null);
      onRefresh();
    } catch (err) {
      setUploadError(`Failed to delete project: ${err}`);
    }
  };

  const handleDeleteDocument = async (docId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(`Delete document "${docId}"?`)) {
      return;
    }

    try {
      await api.deleteDocument(docId);
      onRefresh();
    } catch (err) {
      setUploadError(`Failed to delete document: ${err}`);
    }
  };

  const handleMoveDocument = async (docId: string, toProject: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const doc = documents.find((d) => d.id === docId);
    if (!doc) return;

    const updatedMetadata = { ...doc.metadata };
    if (toProject === 'Uncategorized') {
      delete updatedMetadata.project;
    } else {
      updatedMetadata.project = toProject;
    }

    try {
      await api.updateDocumentMetadata(docId, updatedMetadata);
      onRefresh();
    } catch (err) {
      setUploadError(`Failed to move document: ${err}`);
    }
  };

  const handleUploadToProject = async (e: React.ChangeEvent<HTMLInputElement>, project: string) => {
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
      // Update metadata to assign to project
      if (project !== 'Uncategorized') {
        for (const summary of results) {
          await api.updateDocumentMetadata(summary.id, { ...summary.metadata, project });
        }
      }
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

  // Close menus when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (uploadMenuRef.current && !uploadMenuRef.current.contains(event.target as Node)) {
        setShowUploadMenu(false);
      }
      if (projectMenuRef.current && !projectMenuRef.current.contains(event.target as Node)) {
        setShowProjectMenu(null);
      }
    };

    if (showUploadMenu || showProjectMenu) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [showUploadMenu, showProjectMenu]);

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
        {Array.from(projectGroups.entries()).map(([project, docs]) => (
          <li key={project} className="project-group">
            <div className="project-header">
              <span
                className="project-expand-icon"
                onClick={() => toggleProject(project)}
              >
                {expandedProjects.has(project) ? '▾' : '▸'}
              </span>
              {editingProject === project ? (
                <input
                  type="text"
                  className="project-name-input"
                  value={newProjectName}
                  onChange={(e) => setNewProjectName(e.target.value)}
                  onBlur={() => handleRenameProject(project, newProjectName)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleRenameProject(project, newProjectName);
                    if (e.key === 'Escape') setEditingProject(null);
                  }}
                  autoFocus
                  onClick={(e) => e.stopPropagation()}
                />
              ) : (
                <span
                  className="project-name"
                  onClick={() => toggleProject(project)}
                >
                  {project}
                </span>
              )}
              <span
                className="project-count"
                onClick={() => toggleProject(project)}
              >
                ({docs.length})
              </span>
              <div className="project-actions">
                <button
                  className="project-action-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    setShowProjectMenu(showProjectMenu === project ? null : project);
                  }}
                  title="Project actions"
                >
                  ⋮
                </button>
                {showProjectMenu === project && (
                  <div className="project-menu" ref={projectMenuRef}>
                    <label className="project-menu-item">
                      Add Files
                      <input
                        type="file"
                        accept=".json"
                        onChange={(e) => handleUploadToProject(e, project)}
                        multiple
                        hidden
                      />
                    </label>
                    {project !== 'Uncategorized' && (
                      <>
                        <button
                          className="project-menu-item"
                          onClick={(e) => {
                            e.stopPropagation();
                            setEditingProject(project);
                            setNewProjectName(project);
                            setShowProjectMenu(null);
                          }}
                        >
                          Rename
                        </button>
                        <button
                          className="project-menu-item project-menu-delete"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteProject(project);
                          }}
                        >
                          Delete
                        </button>
                      </>
                    )}
                  </div>
                )}
              </div>
            </div>
            {expandedProjects.has(project) && (
              <ul className="project-docs">
                {docs.map((doc) => (
                  <li
                    key={doc.id}
                    className={`doc-item${doc.id === selectedId ? ' selected' : ''}${doc.is_annotated ? ' annotated' : ''}`}
                    onClick={() => onSelect(doc.id)}
                  >
                    <div className="doc-item-header">
                      <span className="doc-item-id">{doc.id}</span>
                      {doc.is_annotated && <span className="badge">✓</span>}
                      <button
                        className="doc-action-btn"
                        onClick={(e) => handleDeleteDocument(doc.id, e)}
                        title="Delete document"
                      >
                        ×
                      </button>
                    </div>
                    {doc.metadata.category != null && (
                      <div className="doc-category">{String(doc.metadata.category)}</div>
                    )}
                    <select
                      className="doc-project-select"
                      value={String(doc.metadata.project || 'Uncategorized')}
                      onChange={(e) => {
                        const mouseEvent = e.nativeEvent as unknown as React.MouseEvent;
                        handleMoveDocument(doc.id, e.target.value, mouseEvent);
                      }}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {Array.from(projectGroups.keys()).map((p) => (
                        <option key={p} value={p}>
                          {p}
                        </option>
                      ))}
                    </select>
                  </li>
                ))}
              </ul>
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
