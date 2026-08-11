"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ask,
  getHealth,
  uploadPdf,
  getDocuments,
  deleteDocument,
  logout,
  ApiError,
  type HealthResponse,
  type Message,
  type SourceChunk,
} from "@/lib/api";

// Must stay comfortably under the backend's AskRequest.history max_length
// (50, see app/models/schemas.py) so a long-running chat never starts
// failing every request once it crosses that cap.
const MAX_HISTORY_MESSAGES = 20;

export default function Home() {
  const router = useRouter();
  const [authChecked, setAuthChecked] = useState(false);
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [userName, setUserName] = useState<string | null>(null);

  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);

  const [documents, setDocuments] = useState<string[]>([]);
  const [activeDocument, setActiveDocument] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadNote, setUploadNote] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Authenticate token on load
  useEffect(() => {
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("contextiq_token");
      const email = localStorage.getItem("contextiq_email");
      const username = localStorage.getItem("contextiq_username");
      if (!token) {
        router.push("/login");
      } else {
        setUserEmail(email);
        setUserName(username || email?.split("@")[0] || "User");
        setAuthChecked(true);
      }
    }
  }, [router]);

  // Shared handler: if a request failed because the session is gone
  // (expired/invalid token), bounce to /login instead of showing a
  // confusing error in place. Returns true if it handled the error.
  const handleSessionExpiry = useCallback(
    (err: unknown): boolean => {
      if (err instanceof ApiError && err.status === 401) {
        logout();
        router.push("/login");
        return true;
      }
      return false;
    },
    [router],
  );

  const refreshHealth = useCallback(async () => {
    try {
      setHealth(await getHealth());
      setHealthError(null);
    } catch (err) {
      if (handleSessionExpiry(err)) return;
      setHealthError(err instanceof Error ? err.message : "Backend unreachable");
    }
  }, [handleSessionExpiry]);

  const refreshDocuments = useCallback(async () => {
    try {
      const res = await getDocuments();
      setDocuments(res.documents);
      setActiveDocument((prev) => {
        if (prev && res.documents.includes(prev)) return prev;
        return res.documents[0] || null;
      });
    } catch (err) {
      if (handleSessionExpiry(err)) return;
      console.error("Failed to fetch documents list:", err);
    }
  }, [handleSessionExpiry]);

  useEffect(() => {
    if (authChecked) {
      refreshHealth();
      refreshDocuments();
    }
  }, [authChecked, refreshHealth, refreshDocuments]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, asking]);

  async function handleUpload(file: File) {
    setUploading(true);
    setUploadNote(null);
    setUploadError(null);
    try {
      const res = await uploadPdf(file);
      setUploadNote(
        `“${res.filename}” indexed — ${res.pages} page/section(s), ${res.chunks_created} chunks.`,
      );
      setActiveDocument(res.filename);
      setSidebarOpen(false); // Close sidebar drawer on mobile
      await refreshHealth();
      await refreshDocuments();
      setTimeout(() => {
        setUploadNote(null);
      }, 5000);
    } catch (err) {
      if (handleSessionExpiry(err)) return;
      setUploadError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleDelete(doc: string) {
    if (!confirm(`Are you sure you want to delete "${doc}"?`)) return;
    try {
      await deleteDocument(doc);
      if (activeDocument === doc) {
        setActiveDocument(null);
      }
      await refreshHealth();
      await refreshDocuments();
    } catch (err) {
      if (handleSessionExpiry(err)) return;
      alert(err instanceof Error ? err.message : "Failed to delete document");
    }
  }

  async function handleAsk(e: React.FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (!q || asking) return;

    const userMsg: Message = { role: "user", content: q };
    setMessages((prev) => [...prev, userMsg]);
    setQuestion("");
    setAsking(true);
    try {
      // Send recent conversation as history context. Capped at
      // MAX_HISTORY_MESSAGES so it never exceeds the backend's validation
      // limit -- older turns are dropped rather than causing every
      // subsequent question to start failing.
      const recentHistory = messages.slice(-MAX_HISTORY_MESSAGES);
      const res = await ask(q, recentHistory, undefined, activeDocument);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.answer,
          sources: res.sources,
          confidence: res.confidence,
        },
      ]);
    } catch (err) {
      if (handleSessionExpiry(err)) return;
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            "⚠️ " + (err instanceof Error ? err.message : "Something went wrong."),
        },
      ]);
    } finally {
      setAsking(false);
    }
  }

  function handleLogoutClick() {
    logout();
    router.push("/login");
  }

  if (!authChecked) {
    return (
      <div className="flex h-screen w-screen items-center justify-center">
        <span className="dot h-2 w-2 rounded-full bg-fuchsia-300 mr-1" />
        <span className="dot h-2 w-2 rounded-full bg-fuchsia-300 mr-1" style={{ animationDelay: "0.2s" }} />
        <span className="dot h-2 w-2 rounded-full bg-fuchsia-300" style={{ animationDelay: "0.4s" }} />
      </div>
    );
  }

  const indexed = health?.documents_indexed ?? 0;

  return (
    <div className="dashboard-container">
      {/* Mobile Drawer Backdrop Overlay */}
      {sidebarOpen && (
        <div
          className="sidebar-backdrop md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* LEFT COLUMN: SIDEBAR */}
      <aside className={`sidebar-panel p-5 scroll-slim flex flex-col justify-between ${sidebarOpen ? "open" : ""}`}>
        <div className="space-y-6">
          {/* Header / Logo */}
          <header className="flex items-center gap-3 border-b border-white/8 pb-4">
            <div className="glow-violet flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 via-fuchsia-500 to-cyan-400 text-lg font-black text-white">
              IQ
            </div>
            <div className="truncate">
              <h1 className="gradient-text text-xl font-black tracking-tight leading-none">
                ContextIQ
              </h1>
              <p className="text-[10px] text-foreground/45 mt-1">
                Intelligent RAG System
              </p>
            </div>
          </header>

          {/* Connection Status */}
          <div className="flex items-center justify-between gap-3 text-xs bg-white/[0.02] border border-white/5 rounded-xl p-3">
            <span className="text-foreground/50 font-medium">Status</span>
            <StatusBadge health={health} error={healthError} />
          </div>

          {/* Mode Badges */}
          {health && (
            <div className="space-y-1.5">
              <span className="text-[10px] font-semibold text-foreground/40 uppercase tracking-wider block">
                Model Parameters
              </span>
              <div className="flex flex-col gap-1.5">
                <Pill icon="✨">LLM · {health.llm_provider}</Pill>
                <Pill icon="🧬">Embeddings · {health.embedding_provider}</Pill>
                <Pill icon="📚">{indexed} chunks indexed</Pill>
              </div>
            </div>
          )}

          {/* Document Ingestion Zone */}
          <div className="space-y-2">
            <span className="text-[10px] font-semibold text-foreground/40 uppercase tracking-wider block">
              File Ingestion
            </span>
            <label
              onDragOver={(e) => {
                e.preventDefault();
                if (!uploading) setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setIsDragging(false);
                if (uploading) return;
                const f = e.dataTransfer.files?.[0];
                if (f) handleUpload(f);
              }}
              className={`group flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border border-dashed p-5 text-center transition ${
                isDragging
                  ? "border-fuchsia-400 bg-fuchsia-500/10 shadow-lg shadow-fuchsia-500/15"
                  : "border-white/10 hover:border-fuchsia-400/50 hover:bg-white/[0.02]"
              } ${uploading ? "pointer-events-none opacity-60" : ""}`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,.txt,.csv,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/csv"
                disabled={uploading}
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleUpload(f);
                }}
              />
              <span className="text-xl transition group-hover:scale-110">
                {uploading ? "⏳" : "📤"}
              </span>
              <span className="text-xs font-semibold">
                {uploading ? "Processing…" : "Click or drop file"}
              </span>
              <span className="text-[9px] text-foreground/35">PDF, DOCX, TXT, CSV up to 25MB</span>
            </label>

            {uploadNote && (
              <p className="float-in rounded-lg bg-emerald-500/10 border border-emerald-500/20 px-3 py-2 text-xs text-emerald-300">
                {uploadNote}
              </p>
            )}
            {uploadError && (
              <p className="float-in rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2 text-xs text-red-300">
                {uploadError}
              </p>
            )}
          </div>

          {/* Document Database List (History) */}
          <div className="space-y-2">
            <span className="text-[10px] font-semibold text-foreground/40 uppercase tracking-wider block">
              Indexed Documents ({documents.length})
            </span>
            {documents.length === 0 ? (
              <p className="text-xs text-foreground/35 italic py-2">No documents indexed yet.</p>
            ) : (
              <ul className="space-y-1.5 max-h-48 overflow-y-auto scroll-slim">
                {documents.map((doc) => {
                  const isActive = doc === activeDocument;
                  return (
                    <li
                      key={doc}
                      className={`flex items-center justify-between gap-3 rounded-lg transition px-2.5 py-1.5 text-xs border ${
                        isActive
                          ? "border-cyan-500/30 bg-cyan-500/5 ring-1 ring-cyan-500/10 text-cyan-200"
                          : "border-white/5 bg-white/[0.02] text-foreground/80 hover:bg-white/[0.04]"
                      }`}
                    >
                      <button
                        onClick={() => {
                          setActiveDocument(doc);
                          setSidebarOpen(false); // Close sidebar on mobile
                        }}
                        className="truncate flex items-center gap-2 flex-1 text-left cursor-pointer"
                      >
                        <span>
                          {doc.toLowerCase().endsWith(".pdf")
                            ? "📄"
                            : doc.toLowerCase().endsWith(".docx")
                            ? "📝"
                            : doc.toLowerCase().endsWith(".csv")
                            ? "📊"
                            : "🗎"}
                        </span>
                        <span className="truncate font-semibold">{doc}</span>
                        {isActive && (
                          <span className="text-[8px] bg-cyan-500/20 border border-cyan-400/30 text-cyan-400 px-1 py-0.2 rounded-md font-bold uppercase shrink-0">
                            Active
                          </span>
                        )}
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDelete(doc);
                        }}
                        className="text-xs text-red-400 hover:text-red-300 font-semibold p-1 rounded hover:bg-red-500/10 transition cursor-pointer"
                        title="Delete Document"
                      >
                        🗑️
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>

        {/* Footer */}
        <footer className="border-t border-white/6 pt-4 flex flex-col gap-3 mt-4">
          <div className="flex items-center justify-between text-[10px] text-foreground/60 bg-white/[0.02] border border-white/5 rounded-lg px-2.5 py-2">
            <span className="truncate max-w-[180px]" title={userEmail || undefined}>
              👤 Logged in as: {userName}
            </span>
            <button
              onClick={handleLogoutClick}
              className="text-red-400 hover:text-red-300 font-bold transition cursor-pointer"
            >
              Log Out
            </button>
          </div>
          <div className="text-center text-[9px] text-foreground/25">
            ContextIQ v1.0 · Strict Grounded Mode - by Prafull Shukla
          </div>
        </footer>
      </aside>

      {/* RIGHT COLUMN: CHAT PANEL */}
      <main className="chat-canvas">
        {/* Top Header */}
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-white/6 px-4 bg-white/[0.01]">
          <div className="flex items-center gap-2 truncate">
            {/* Mobile Sidebar Hamburger Toggle */}
            <button
              onClick={() => setSidebarOpen(true)}
              className="md:hidden p-2 text-foreground/80 hover:text-foreground hover:bg-white/5 rounded-lg transition mr-1 cursor-pointer"
              title="Open Sidebar"
            >
              ☰
            </button>
            <h2 className="text-sm font-semibold tracking-tight text-foreground/85 flex items-center gap-2 shrink-0">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-cyan-400 opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-cyan-400" />
              </span>
              Active Chat Session
            </h2>
            {activeDocument ? (
              <span className="text-[10px] text-cyan-300 bg-cyan-500/10 px-2.5 py-0.5 rounded-full border border-cyan-500/20 truncate max-w-[140px] sm:max-w-[220px]" title={activeDocument}>
                Focusing on: {activeDocument}
              </span>
            ) : (
              <span className="text-[10px] text-foreground/30 bg-white/[0.02] px-2.5 py-0.5 rounded-full border border-white/5">
                No active document
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <span className="text-[10px] text-foreground/40 font-mono hidden sm:inline">
              {messages.length} message{messages.length !== 1 ? "s" : ""}
            </span>
            {messages.length > 0 && (
              <button
                onClick={() => setMessages([])}
                className="text-[10px] font-semibold text-red-400/90 hover:text-red-300 bg-red-500/10 hover:bg-red-500/15 border border-red-500/20 rounded-lg px-2.5 py-1 transition cursor-pointer"
                title="Clear current chat history"
              >
                Clear Chat
              </button>
            )}
          </div>
        </header>

        {/* Chat Messages Scrolling Box */}
        <div className="scroll-slim flex-1 space-y-5 overflow-y-auto p-6">
          {messages.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center gap-3 py-16 text-center">
              <span className="text-4xl opacity-50">💬</span>
              <div>
                <h3 className="text-sm font-semibold text-foreground/70">Start a Conversation</h3>
                <p className="text-xs text-foreground/35 mt-1 max-w-sm">
                  {activeDocument
                    ? `Ask a question. Answers will be strictly grounded within "${activeDocument}".`
                    : "Please upload and index a document in the sidebar to begin."}
                </p>
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <Bubble key={i} role={m.role} content={m.content} sources={m.sources} confidence={m.confidence} />
          ))}
          {asking && <Thinking />}
          <div ref={chatEndRef} />
        </div>

        {/* Query Input Section */}
        <div className="border-t border-white/6 p-4 bg-white/[0.005]">
          <form onSubmit={handleAsk} className="mx-auto max-w-2xl flex gap-2">
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder={activeDocument ? `Ask about "${activeDocument}"...` : "Upload a file to ask questions..."}
              className="flex-1 rounded-xl border border-white/8 bg-white/[0.02] px-4 py-2.5 text-xs outline-none transition placeholder:text-foreground/30 focus:border-fuchsia-400/40 focus:bg-white/[0.04]"
              disabled={!activeDocument || asking}
            />
            <button
              type="submit"
              disabled={asking || !question.trim() || !activeDocument}
              className="rounded-xl bg-gradient-to-r from-violet-500 to-fuchsia-500 px-5 py-2.5 text-xs font-semibold text-white shadow-lg shadow-fuchsia-500/20 transition hover:shadow-fuchsia-500/35 hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
            >
              Send
            </button>
          </form>
          <div className="mt-2 text-center text-[10px] text-foreground/30">
            This chatbot is fully grounded in your document base. Web search triggers automatically if query context is missing.
          </div>
        </div>
      </main>
    </div>
  );
}

function StatusBadge({
  health,
  error,
}: {
  health: HealthResponse | null;
  error: string | null;
}) {
  const ok = !!health && !error;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-medium leading-none ${
        ok
          ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
          : "border-red-500/20 bg-red-500/10 text-red-400"
      }`}
      title={error ?? undefined}
    >
      <span className="relative flex h-1.5 w-1.5">
        {ok && (
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
        )}
        <span
          className={`relative inline-flex h-1.5 w-1.5 rounded-full ${
            ok ? "bg-emerald-400" : "bg-red-400"
          }`}
        />
      </span>
      {ok ? "Connected" : "Offline"}
    </span>
  );
}

function Pill({
  children,
  icon,
}: {
  children: React.ReactNode;
  icon: string;
}) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-lg border border-white/6 bg-white/[0.02] px-2.5 py-1 text-[10px] text-foreground/60">
      <span>{icon}</span>
      <span className="truncate">{children}</span>
    </span>
  );
}

function Bubble({
  role,
  content,
  sources,
  confidence,
}: {
  role: "user" | "assistant";
  content: string;
  sources?: SourceChunk[] | null;
  confidence?: number | null;
}) {
  const isUser = role === "user";
  const [showSources, setShowSources] = useState(false);

  return (
    <div className={`float-in flex flex-col gap-1.5 ${isUser ? "items-end" : "items-start"}`}>
      {/* Bubble text */}
      <div className={`flex w-full ${isUser ? "justify-end" : "justify-start"}`}>
        <div
          className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-xs leading-relaxed ${
            isUser
              ? "rounded-br-sm bg-gradient-to-br from-violet-500 to-fuchsia-500 text-white shadow-lg shadow-fuchsia-500/20"
              : "rounded-bl-sm border border-white/8 bg-white/[0.04] text-foreground/90 glass-card"
          }`}
        >
          {content}
        </div>
      </div>

      {/* Citations metadata under bubble */}
      {!isUser && ((sources && sources.length > 0) || (confidence !== undefined && confidence !== null)) && (
        <div className="mx-2 flex flex-col gap-1 text-[10px] text-foreground/50 max-w-[80%]">
          <div className="flex items-center gap-2.5 flex-wrap">
            {confidence !== undefined && confidence !== null && confidence > 0 && (
              <span className="font-semibold text-cyan-400 bg-cyan-500/10 px-2 py-0.5 rounded-full border border-cyan-500/20">
                🎯 {Math.round(confidence * 100)}% Grounded
              </span>
            )}
            {sources && sources.length > 0 && (
              <button
                onClick={() => setShowSources(!showSources)}
                className="hover:text-foreground underline transition font-medium cursor-pointer"
              >
                {showSources ? "Hide Citations ▲" : `Show ${sources.length} Citation${sources.length > 1 ? "s" : ""} ▼`}
              </button>
            )}
          </div>

          {/* Collapsible sources list */}
          {showSources && sources && (
            <div className="float-in mt-1.5 rounded-xl border border-white/5 bg-white/[0.02] p-2.5 space-y-2 max-h-48 overflow-y-auto scroll-slim">
              {sources.map((s, idx) => (
                <div key={idx} className="border-b border-white/5 pb-2 last:border-b-0 last:pb-0">
                  <div className="flex items-center justify-between gap-2 font-semibold text-foreground/60 mb-0.5">
                    <span className="truncate">📖 {s.source}</span>
                    <span className="shrink-0 text-foreground/40 font-mono text-[9px]">
                      {s.page !== undefined && s.page !== null ? `Page ${s.page + 1}` : ""}
                      {s.score ? ` (Score: ${Math.round(s.score * 100)}%)` : ""}
                    </span>
                  </div>
                  <p className="italic text-foreground/45 leading-normal font-mono text-[9px] break-words">
                    "{s.content}"
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Thinking() {
  return (
    <div className="float-in flex justify-start">
      <div className="flex items-center gap-1.5 rounded-2xl rounded-bl-sm border border-white/8 bg-white/[0.04] px-4 py-3 glass-card">
        <span className="dot h-1.5 w-1.5 rounded-full bg-fuchsia-300" />
        <span
          className="dot h-1.5 w-1.5 rounded-full bg-fuchsia-300"
          style={{ animationDelay: "0.2s" }}
        />
        <span
          className="dot h-1.5 w-1.5 rounded-full bg-fuchsia-300"
          style={{ animationDelay: "0.4s" }}
        />
      </div>
    </div>
  );
}
