import { loadToken } from "./auth-storage";
import type {
  AllowedEmail,
  ConversationDetail,
  ConversationOut,
  DocumentOut,
  LoginResponse,
  QueryResponse,
  User,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export class UnauthorizedError extends Error {}

function authHeaders(extra?: HeadersInit): Headers {
  const h = new Headers(extra);
  const token = loadToken();
  if (token) h.set("authorization", `Bearer ${token}`);
  return h;
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = authHeaders(init?.headers);
  if (init?.body && !headers.has("content-type")) headers.set("content-type", "application/json");
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (res.status === 401) throw new UnauthorizedError("session expired");
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${body || path}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  googleLogin: (idToken: string) =>
    http<LoginResponse>("/api/auth/google", { method: "POST", body: JSON.stringify({ id_token: idToken }) }),
  me: () => http<User>("/api/auth/me"),

  listDocuments: () => http<DocumentOut[]>("/api/documents"),
  getDocument: (id: string) => http<DocumentOut>(`/api/documents/${id}`),
  deleteDocument: (id: string) => http<void>(`/api/documents/${id}`, { method: "DELETE" }),
  downloadDocument: async (id: string): Promise<Blob> => {
    const res = await fetch(`${BASE}/api/documents/${id}/file`, { headers: authHeaders() });
    if (res.status === 401) throw new UnauthorizedError("session expired");
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.blob();
  },
  uploadDocument: async (file: File): Promise<DocumentOut> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/api/documents`, { method: "POST", body: form, headers: authHeaders() });
    if (res.status === 401) throw new UnauthorizedError("session expired");
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${await res.text().catch(() => "")}`);
    return res.json();
  },

  query: (text: string, conversationId: string | null) =>
    http<QueryResponse>("/api/query", {
      method: "POST",
      body: JSON.stringify({ text, conversation_id: conversationId }),
    }),

  listConversations: () => http<ConversationOut[]>("/api/conversations"),
  getConversation: (id: string) => http<ConversationDetail>(`/api/conversations/${id}`),

  listAllowlist: () => http<AllowedEmail[]>("/api/admin/allowlist"),
  addAllowedEmail: (email: string) =>
    http<AllowedEmail>("/api/admin/allowlist", { method: "POST", body: JSON.stringify({ email }) }),
  removeAllowedEmail: (email: string) =>
    http<void>(`/api/admin/allowlist/${encodeURIComponent(email)}`, { method: "DELETE" }),
};
