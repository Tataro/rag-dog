export type DocumentStatus = "uploading" | "processing" | "ready" | "failed";

export interface DocumentOut {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  status: DocumentStatus;
  error: string | null;
  page_count: number | null;
  created_at: string;
  indexed_at: string | null;
}

export interface Citation {
  marker: number;
  chunk_id: string;
  document_id: string;
  filename: string;
  page: number | null;
  section: string | null;
  snippet: string;
}

export interface QueryResponse {
  answer: string;
  citations: Citation[];
  conversation_id: string;
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
}

export interface ConversationOut {
  id: string;
  preview: string;
  created_at: string;
  last_message_at: string;
}

export interface MessageOut {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[] | null;
  created_at: string;
}

export interface ConversationDetail {
  id: string;
  created_at: string;
  messages: MessageOut[];
}

export interface User {
  id: string;
  email: string;
  name: string | null;
  picture: string | null;
  is_admin: boolean;
}

export interface LoginResponse {
  session_token: string;
  user: User;
}

export interface AllowedEmail {
  email: string;
  created_at: string;
}
