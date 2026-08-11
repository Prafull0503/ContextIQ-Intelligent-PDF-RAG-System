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

/**
 * Error thrown for any non-OK API response. Carries the HTTP status code so
 * callers can branch on it (e.g. `err.status === 401`) instead of pattern
 * -matching on the message text, which breaks the moment the backend's
 * error message doesn't happen to contain the status code as a substring.
 */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const TOKEN_KEY = "contextiq_token";
const EMAIL_KEY = "contextiq_email";
const USERNAME_KEY = "contextiq_username";

/** Get authentication headers if JWT token is stored in localStorage. */
function getAuthHeaders(): HeadersInit {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) {
      return { Authorization: `Bearer ${token}` };
    }
  }
  return {};
}

/** Drop the locally stored session (used on logout and on 401 responses). */
function clearSession(): void {
  if (typeof window !== "undefined") {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(EMAIL_KEY);
    localStorage.removeItem(USERNAME_KEY);
  }
}

/**
 * Wrapper around window.fetch that automatically injects JWT bearer tokens
 * and clears a stale/expired session on 401 responses.
 *
 * Headers are merged via the `Headers` API rather than object-spreading
 * `options.headers`, because `HeadersInit` can legally be a `Headers`
 * instance or an array of tuples -- spreading either of those silently
 * drops the entries instead of merging them.
 */
async function fetchWithAuth(url: string, options: RequestInit = {}): Promise<Response> {
  const merged = new Headers(options.headers);
  const authHeaders = getAuthHeaders();
  for (const [key, value] of Object.entries(authHeaders)) {
    if (!merged.has(key)) merged.set(key, value);
  }

  const res = await fetch(url, { ...options, headers: merged });

  if (res.status === 401 && typeof window !== "undefined") {
    // Session is gone server-side (expired/invalid token) -- don't leave a
    // dead token sitting in localStorage making the UI look logged-in.
    clearSession();
  }

  return res;
}

/**
 * Pull `detail` out of the backend's error envelope, falling back to status text.
 *
 * Two shapes are possible here:
 *  - Our own domain errors (RAGError etc.) -> `{ detail: "some message" }`.
 *  - FastAPI/Pydantic request-validation failures (422) -> `{ detail: [{ loc, msg, type }, ...] }`.
 */
async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (body && typeof body.detail === "string") return body.detail;
    if (body && Array.isArray(body.detail)) {
      const messages = body.detail
        .map((e: { msg?: string }) => e?.msg)
        .filter((msg: unknown): msg is string => typeof msg === "string");
      if (messages.length > 0) return messages.join("; ");
    }
  } catch {
    /* response wasn't JSON — fall through */
  }
  return `Request failed (${res.status} ${res.statusText})`;
}

/** Throw an `ApiError` (message + status code) for a non-OK response. */
async function throwForStatus(res: Response): Promise<never> {
  throw new ApiError(await parseError(res), res.status);
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
  if (!res.ok) await throwForStatus(res);
  return res.json();
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  const res = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) await throwForStatus(res);
  const data: TokenResponse = await res.json();
  if (typeof window !== "undefined") {
    localStorage.setItem(TOKEN_KEY, data.access_token);
    localStorage.setItem(EMAIL_KEY, email);
    localStorage.setItem(USERNAME_KEY, data.username || email.split("@")[0]);
  }
  return data;
}

export function logout(): void {
  clearSession();
}

// ---------------------------------------------------------------------------
// Protected RAG APIs
// ---------------------------------------------------------------------------

export async function getHealth(): Promise<HealthResponse> {
  const res = await fetchWithAuth(`${API_URL}/health`, { cache: "no-store" });
  if (!res.ok) await throwForStatus(res);
  return res.json();
}

export async function uploadPdf(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetchWithAuth(`${API_URL}/upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) await throwForStatus(res);
  return res.json();
}

export async function getDocuments(): Promise<DocumentListResponse> {
  const res = await fetchWithAuth(`${API_URL}/documents`, { cache: "no-store" });
  if (!res.ok) await throwForStatus(res);
  return res.json();
}

export async function deleteDocument(filename: string): Promise<DeleteDocumentResponse> {
  const res = await fetchWithAuth(`${API_URL}/documents/${encodeURIComponent(filename)}`, {
    method: "DELETE",
  });
  if (!res.ok) await throwForStatus(res);
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
  if (!res.ok) await throwForStatus(res);
  return res.json();
}
