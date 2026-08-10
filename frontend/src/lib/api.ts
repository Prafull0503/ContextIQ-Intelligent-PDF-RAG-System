/**
 * Typed client for the ContextIQ FastAPI backend.
 */

const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

export interface HealthResponse {
  status: string;
  llm_provider: string;
  embedding_provider: string;
  documents_indexed: number;
}

export interface UploadResponse {
  message: string;
  filename: string;
  chunks_created: number;
  pages: number;
}

export interface SourceChunk {
  content: string;
  source: string;
  page?: number | null;
  score?: number | null;
}

export interface AskResponse {
  answer: string;
  sources?: SourceChunk[] | null;
  confidence?: number | null;
}

export interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: SourceChunk[] | null;
  confidence?: number | null;
}

export interface DocumentListResponse {
  documents: string[];
}

export interface DeleteDocumentResponse {
  message: string;
  filename: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  username?: string;
}

export interface UserResponse {
  id: number;
  email: string;
  username: string;
  created_at: string;
}

/** Get authentication headers if JWT token is stored in localStorage. */
function getAuthHeaders(): HeadersInit {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("contextiq_token");
    if (token) {
      return { Authorization: `Bearer ${token}` };
    }
  }
  return {};
}

/** Wrapper around window.fetch that automatically injects JWT bearer tokens. */
async function fetchWithAuth(url: string, options: RequestInit = {}): Promise<Response> {
  const headers = {
    ...getAuthHeaders(),
    ...options.headers,
  };
  return fetch(url, { ...options, headers });
}

/** Pull `detail` out of the backend's error envelope, falling back to status text. */
async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (body && typeof body.detail === "string") return body.detail;
  } catch {
    /* response wasn't JSON — fall through */
  }
  return `Request failed (${res.status} ${res.statusText})`;
}

// ---------------------------------------------------------------------------
// Authentication APIs
// ---------------------------------------------------------------------------

export async function signup(email: string, password: string, username: string): Promise<UserResponse> {
  const res = await fetch(`${API_URL}/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, username }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  const res = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  const data: TokenResponse = await res.json();
  if (typeof window !== "undefined") {
    localStorage.setItem("contextiq_token", data.access_token);
    localStorage.setItem("contextiq_email", email);
    localStorage.setItem("contextiq_username", data.username || email.split("@")[0]);
  }
  return data;
}

export function logout(): void {
  if (typeof window !== "undefined") {
    localStorage.removeItem("contextiq_token");
    localStorage.removeItem("contextiq_email");
    localStorage.removeItem("contextiq_username");
  }
}

// ---------------------------------------------------------------------------
// Protected RAG APIs
// ---------------------------------------------------------------------------

export async function getHealth(): Promise<HealthResponse> {
  const res = await fetchWithAuth(`${API_URL}/health`, { cache: "no-store" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function uploadPdf(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetchWithAuth(`${API_URL}/upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function getDocuments(): Promise<DocumentListResponse> {
  const res = await fetchWithAuth(`${API_URL}/documents`, { cache: "no-store" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function deleteDocument(filename: string): Promise<DeleteDocumentResponse> {
  const res = await fetchWithAuth(`${API_URL}/documents/${encodeURIComponent(filename)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function ask(
  question: string,
  history: Message[] = [],
  topK?: number,
  selectedDocument?: string | null,
): Promise<AskResponse> {
  const res = await fetchWithAuth(`${API_URL}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      history,
      top_k: topK ?? null,
      selected_document: selectedDocument ?? null,
    }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}
