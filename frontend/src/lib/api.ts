/**
 * Typed client for the ContextIQ FastAPI backend.
 *
 * The base URL comes from NEXT_PUBLIC_API_URL (see .env.local) and defaults to
 * the local dev server. Each function maps 1:1 to a backend endpoint and mirrors
 * the Pydantic schemas in app/models/schemas.py.
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

export interface AskResponse {
  answer: string;
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

export async function getHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_URL}/health`, { cache: "no-store" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function uploadPdf(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_URL}/upload-pdf`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function ask(
  question: string,
  topK?: number,
): Promise<AskResponse> {
  const res = await fetch(`${API_URL}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, top_k: topK ?? null }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}
