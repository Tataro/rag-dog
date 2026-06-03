import { config } from "./config";
import { loadToken } from "./auth-storage";
import type { ConversationDetail, ConversationOut, DocumentOut, LoginResponse, QueryResponse, User } from "./types";

export class UnauthorizedError extends Error {}

async function authHeaders(extra?: HeadersInit): Promise<Headers> {
  const h = new Headers(extra);
  const token = await loadToken();
  if (token) h.set("authorization", `Bearer ${token}`);
  return h;
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = await authHeaders(init?.headers);
  if (init?.body && !headers.has("content-type")) headers.set("content-type", "application/json");
  const res = await fetch(`${config.apiBase}${path}`, { ...init, headers });
  if (res.status === 401) throw new UnauthorizedError("session expired");
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${await res.text().catch(() => "")}`);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  googleLogin: (idToken: string) =>
    http<LoginResponse>("/api/auth/google", { method: "POST", body: JSON.stringify({ id_token: idToken }) }),
  me: () => http<User>("/api/auth/me"),
  listDocuments: () => http<DocumentOut[]>("/api/documents"),
  deleteDocument: (id: string) => http<void>(`/api/documents/${id}`, { method: "DELETE" }),
  query: (text: string, conversationId: string | null) =>
    http<QueryResponse>("/api/query", { method: "POST", body: JSON.stringify({ text, conversation_id: conversationId }) }),
  listConversations: () => http<ConversationOut[]>("/api/conversations"),
  getConversation: (id: string) => http<ConversationDetail>(`/api/conversations/${id}`),
  uploadDocument: async (file: { uri: string; name: string; mimeType: string }): Promise<DocumentOut> => {
    const form = new FormData();
    form.append("file", { uri: file.uri, name: file.name, type: file.mimeType } as unknown as Blob);
    const headers = await authHeaders();
    const res = await fetch(`${config.apiBase}/api/documents`, { method: "POST", body: form, headers });
    if (res.status === 401) throw new UnauthorizedError("session expired");
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return await res.json();
  },
};
