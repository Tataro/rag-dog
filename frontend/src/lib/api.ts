import type { DocumentOut, QueryResponse } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${body || path}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  listDocuments: () => http<DocumentOut[]>("/api/documents"),
  getDocument: (id: string) => http<DocumentOut>(`/api/documents/${id}`),
  deleteDocument: (id: string) =>
    http<void>(`/api/documents/${id}`, { method: "DELETE" }),
  uploadDocument: async (file: File): Promise<DocumentOut> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/api/documents`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new Error(`${res.status} ${res.statusText}: ${body}`);
    }
    return res.json();
  },
  query: (text: string, sessionId: string) =>
    http<QueryResponse>("/api/query", {
      method: "POST",
      body: JSON.stringify({ text, session_id: sessionId }),
    }),
};
