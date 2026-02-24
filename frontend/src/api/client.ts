import type {
  AnnotationFile,
  Document,
  DocumentSummary,
  TerminologyConcept,
  TerminologyInfo,
} from '../types';

const BASE = '/api';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listDocuments: () => request<DocumentSummary[]>('/documents'),

  uploadDocuments: (files: File[]) => {
    const form = new FormData();
    files.forEach((file) => form.append('files', file));
    return request<DocumentSummary[]>('/documents/upload', { method: 'POST', body: form });
  },

  getDocument: (docId: string) => request<Document>(`/documents/${docId}`),

  updateDocumentMetadata: (docId: string, metadata: Record<string, unknown>) =>
    request<Document>(`/documents/${docId}/metadata`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ metadata }),
    }),

  deleteDocument: (docId: string) =>
    request<{ status: string; doc_id: string }>(`/documents/${docId}`, {
      method: 'DELETE',
    }),

  getAnnotations: (docId: string) =>
    request<AnnotationFile>(`/documents/${docId}/annotations`),

  saveAnnotations: (docId: string, ann: AnnotationFile) =>
    request<AnnotationFile>(`/documents/${docId}/annotations`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(ann),
    }),

  preannotateDocument: (docId: string) =>
    request<AnnotationFile>(`/documents/${docId}/preannotate`, {
      method: 'POST',
    }),

  searchTerminology: (q: string, limit = 20) =>
    request<TerminologyConcept[]>(
      `/terminology/search?q=${encodeURIComponent(q)}&limit=${limit}`
    ),

  getTerminologyInfo: () => request<TerminologyInfo>('/terminology/info'),

  uploadTerminology: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request<TerminologyInfo>('/terminology/upload', { method: 'POST', body: form });
  },

  exportProject: (projectName: string | null) => {
    const params = projectName ? `?project=${encodeURIComponent(projectName)}` : '';
    return fetch(`${BASE}/documents/export${params}`)
      .then(res => {
        if (!res.ok) throw new Error(`Export failed: ${res.statusText}`);
        return res.blob();
      })
      .then(blob => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${projectName || 'all-documents'}.zip`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
      });
  },
};
