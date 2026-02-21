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

  uploadDocument: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request<DocumentSummary>('/documents/upload', { method: 'POST', body: form });
  },

  getDocument: (docId: string) => request<Document>(`/documents/${docId}`),

  getAnnotations: (docId: string) =>
    request<AnnotationFile>(`/documents/${docId}/annotations`),

  saveAnnotations: (docId: string, ann: AnnotationFile) =>
    request<AnnotationFile>(`/documents/${docId}/annotations`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(ann),
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
};
