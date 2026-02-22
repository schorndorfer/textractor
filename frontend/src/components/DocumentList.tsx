import { useState, useEffect, useRef } from 'react';
import { api } from '../api/client';
import type { DocumentSummary } from '../types';

interface AddFilesDialogProps {
  projectName: string;
  allDocuments: DocumentSummary[];
  currentProjectDocs: DocumentSummary[];
  onAdd: (docIds: string[]) => void;
  onClose: () => void;
  dialogRef: React.RefObject<HTMLDivElement | null>;
}

function AddFilesDialog({ projectName, allDocuments, currentProjectDocs, onAdd, onClose, dialogRef }: AddFilesDialogProps) {
  const [selectedDocs, setSelectedDocs] = useState<Set<string>>(new Set());

  const currentDocIds = new Set(currentProjectDocs.map((d) => d.id));
  const availableDocs = allDocuments.filter((d) => !currentDocIds.has(d.id));

  const toggleDoc = (docId: string) => {
    setSelectedDocs((prev) => {
      const next = new Set(prev);
      if (next.has(docId)) {
        next.delete(docId);
      } else {
        next.add(docId);
      }
      return next;
    });
  };

  const handleAdd = () => {
    onAdd(Array.from(selectedDocs));
  };

  return (
    <div className="add-files-dialog-backdrop">
      <div className="add-files-dialog" ref={dialogRef}>
        <div className="add-files-dialog-header">
          <h3>Add Files to {projectName}</h3>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        <div className="add-files-dialog-body">
          {availableDocs.length === 0 ? (
            <p className="empty-hint">No documents available to add</p>
          ) : (
            <ul className="add-files-list">
              {availableDocs.map((doc) => (
                <li key={doc.id} className="add-files-item">
                  <label className="add-files-checkbox-label">
                    <input
                      type="checkbox"
                      checked={selectedDocs.has(doc.id)}
                      onChange={() => toggleDoc(doc.id)}
                    />
                    <span className="add-files-doc-info">
                      <span className="add-files-doc-id">{doc.id}</span>
                      {doc.metadata.category != null && (
                        <span className="add-files-doc-category">{String(doc.metadata.category)}</span>
                      )}
                      <span className="add-files-doc-project">
                        From: {doc.metadata.project != null ? String(doc.metadata.project) : 'Uncategorized'}
                      </span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="add-files-dialog-footer">
          <button className="cancel-btn" onClick={onClose}>Cancel</button>
          <button
            className="add-btn"
            onClick={handleAdd}
            disabled={selectedDocs.size === 0}
          >
            Add {selectedDocs.size > 0 && `(${selectedDocs.size})`}
          </button>
        </div>
      </div>
    </div>
  );
}

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
  const [emptyProjects, setEmptyProjects] = useState<Set<string>>(new Set());
  const [editingProject, setEditingProject] = useState<string | null>(null);
  const [newProjectName, setNewProjectName] = useState('');
  const [showProjectMenu, setShowProjectMenu] = useState<string | null>(null);
  const [showAddFilesDialog, setShowAddFilesDialog] = useState<string | null>(null);
  const [creatingProject, setCreatingProject] = useState(false);
  const [createProjectName, setCreateProjectName] = useState('');
  const uploadMenuRef = useRef<HTMLDivElement>(null);
  const projectMenuRef = useRef<HTMLDivElement>(null);
  const addFilesDialogRef = useRef<HTMLDivElement>(null);

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

  // Add empty projects to the groups
  emptyProjects.forEach((project) => {
    if (!projectGroups.has(project)) {
      projectGroups.set(project, []);
    }
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
    const trimmedNewName = newName.trim();
    if (!trimmedNewName || trimmedNewName === oldName) {
      setEditingProject(null);
      return;
    }

    if (trimmedNewName === 'Uncategorized') {
      setUploadError('Cannot rename a project to "Uncategorized"');
      setEditingProject(null);
      return;
    }

    // Check if new name already exists
    if (projectGroups.has(trimmedNewName) || emptyProjects.has(trimmedNewName)) {
      setUploadError(`Project "${trimmedNewName}" already exists`);
      setEditingProject(null);
      return;
    }

    const docsInProject = projectGroups.get(oldName) || [];
    const isEmptyProject = docsInProject.length === 0;

    try {
      if (isEmptyProject) {
        // Just update the empty projects set
        setEmptyProjects((prev) => {
          const next = new Set(prev);
          next.delete(oldName);
          next.add(trimmedNewName);
          return next;
        });
        // Update expanded state
        setExpandedProjects((prev) => {
          const next = new Set(prev);
          if (next.has(oldName)) {
            next.delete(oldName);
            next.add(trimmedNewName);
          }
          return next;
        });
      } else {
        // Update all documents in the project
        for (const doc of docsInProject) {
          await api.updateDocumentMetadata(doc.id, { project: trimmedNewName });
        }
        onRefresh();
      }
      setEditingProject(null);
    } catch (err) {
      setUploadError(`Failed to rename project: ${err}`);
      setEditingProject(null);
    }
  };

  const handleDeleteProject = async (projectName: string) => {
    if (projectName === 'Uncategorized') {
      setUploadError('Cannot delete the Uncategorized project');
      return;
    }

    const docsInProject = projectGroups.get(projectName) || [];
    const isEmptyProject = docsInProject.length === 0;

    const confirmMessage = isEmptyProject
      ? `Delete empty project "${projectName}"?`
      : `Delete project "${projectName}"? ${docsInProject.length} document(s) will be moved to Uncategorized.`;

    if (!confirm(confirmMessage)) {
      return;
    }

    try {
      // Move documents to Uncategorized
      for (const doc of docsInProject) {
        const updatedMetadata = { ...doc.metadata };
        delete updatedMetadata.project;
        await api.updateDocumentMetadata(doc.id, updatedMetadata);
      }

      // Remove from empty projects if it's there
      setEmptyProjects((prev) => {
        const next = new Set(prev);
        next.delete(projectName);
        return next;
      });

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

  const handleCreateProject = (e?: React.FormEvent) => {
    e?.preventDefault();
    const projectName = createProjectName.trim();
    if (!projectName) {
      setCreatingProject(false);
      return;
    }

    if (projectName === 'Uncategorized') {
      setUploadError('Cannot create a project named "Uncategorized"');
      setCreateProjectName('');
      return;
    }

    // Check if project already exists
    if (projectGroups.has(projectName) || emptyProjects.has(projectName)) {
      setUploadError(`Project "${projectName}" already exists`);
      setCreateProjectName('');
      return;
    }

    // Add to empty projects and expand it
    setEmptyProjects((prev) => new Set(prev).add(projectName));
    setExpandedProjects((prev) => new Set(prev).add(projectName));
    setCreatingProject(false);
    setCreateProjectName('');
  };

  const handleAddFilesToProject = async (projectName: string, docIds: string[]) => {
    if (docIds.length === 0) return;

    try {
      for (const docId of docIds) {
        const doc = documents.find((d) => d.id === docId);
        if (!doc) continue;

        const updatedMetadata = { ...doc.metadata };
        if (projectName === 'Uncategorized') {
          delete updatedMetadata.project;
        } else {
          updatedMetadata.project = projectName;
        }
        await api.updateDocumentMetadata(docId, updatedMetadata);
      }

      // Remove from empty projects once files are added
      if (projectName !== 'Uncategorized') {
        setEmptyProjects((prev) => {
          const next = new Set(prev);
          next.delete(projectName);
          return next;
        });
      }

      setShowAddFilesDialog(null);
      onRefresh();
    } catch (err) {
      setUploadError(`Failed to add files: ${err}`);
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
      if (addFilesDialogRef.current && !addFilesDialogRef.current.contains(event.target as Node)) {
        setShowAddFilesDialog(null);
      }
    };

    if (showUploadMenu || showProjectMenu || showAddFilesDialog) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [showUploadMenu, showProjectMenu, showAddFilesDialog]);

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
      <div className="create-project-container">
        {creatingProject ? (
          <form onSubmit={handleCreateProject} className="create-project-form">
            <input
              type="text"
              className="create-project-input"
              placeholder="Enter project name..."
              value={createProjectName}
              onChange={(e) => setCreateProjectName(e.target.value)}
              onBlur={() => {
                if (createProjectName.trim()) {
                  handleCreateProject();
                } else {
                  setCreatingProject(false);
                }
              }}
              onKeyDown={(e) => {
                if (e.key === 'Escape') {
                  setCreatingProject(false);
                  setCreateProjectName('');
                }
              }}
              autoFocus
            />
          </form>
        ) : (
          <button
            className="create-project-btn"
            onClick={() => setCreatingProject(true)}
          >
            + New Project
          </button>
        )}
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
                    <button
                      className="project-menu-item"
                      onClick={(e) => {
                        e.stopPropagation();
                        setShowAddFilesDialog(project);
                        setShowProjectMenu(null);
                      }}
                    >
                      Add Files
                    </button>
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
                {showAddFilesDialog === project && (
                  <AddFilesDialog
                    projectName={project}
                    allDocuments={documents}
                    currentProjectDocs={docs}
                    onAdd={(docIds) => handleAddFilesToProject(project, docIds)}
                    onClose={() => setShowAddFilesDialog(null)}
                    dialogRef={addFilesDialogRef}
                  />
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
