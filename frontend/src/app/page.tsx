"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ask,
  getHealth,
  uploadPdf,
  type HealthResponse,
} from "@/lib/api";

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
}

export default function Home() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);

  const [uploading, setUploading] = useState(false);
  const [uploadNote, setUploadNote] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const refreshHealth = useCallback(async () => {
    try {
      setHealth(await getHealth());
      setHealthError(null);
    } catch (err) {
      setHealthError(err instanceof Error ? err.message : "Backend unreachable");
    }
  }, []);

  useEffect(() => {
    refreshHealth();
  }, [refreshHealth]);

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
        `“${res.filename}” indexed — ${res.pages} page(s), ${res.chunks_created} chunks.`,
      );
      await refreshHealth();
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleAsk(e: React.FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (!q || asking) return;

    setMessages((prev) => [...prev, { role: "user", text: q }]);
    setQuestion("");
    setAsking(true);
    try {
      const res = await ask(q);
      setMessages((prev) => [...prev, { role: "assistant", text: res.answer }]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text:
            "⚠️ " + (err instanceof Error ? err.message : "Something went wrong."),
        },
      ]);
    } finally {
      setAsking(false);
    }
  }

  const indexed = health?.documents_indexed ?? 0;

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-4 py-10">
      {/* Header */}
      <header className="flex flex-col gap-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="glow-violet flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500 via-fuchsia-500 to-cyan-400 text-xl font-black text-white">
              IQ
            </div>
            <div>
              <h1 className="gradient-text text-3xl font-black tracking-tight">
                ContextIQ
              </h1>
              <p className="text-sm text-foreground/55">
                Upload a PDF, then chat with its content.
              </p>
            </div>
          </div>
          <StatusBadge health={health} error={healthError} />
        </div>

        {health && (
          <div className="flex flex-wrap gap-2 text-xs">
            <Pill icon="✨">LLM · {health.llm_provider}</Pill>
            <Pill icon="🧬">Embeddings · {health.embedding_provider}</Pill>
            <Pill icon="📚">{indexed} chunks indexed</Pill>
          </div>
        )}
      </header>

      {/* Upload */}
      <section className="glass rounded-2xl p-5">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground/80">
          <span className="grid h-6 w-6 place-items-center rounded-full bg-violet-500/20 text-xs text-violet-300">
            1
          </span>
          Upload a PDF
        </h2>

        <label
          className={`group flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-white/15 px-6 py-7 text-center transition hover:border-fuchsia-400/50 hover:bg-white/[0.03] ${
            uploading ? "pointer-events-none opacity-60" : ""
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept="application/pdf,.pdf"
            disabled={uploading}
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleUpload(f);
            }}
          />
          <span className="text-2xl transition group-hover:scale-110">
            {uploading ? "⏳" : "📄"}
          </span>
          <span className="text-sm font-medium">
            {uploading ? "Processing…" : "Click to choose a PDF"}
          </span>
          <span className="text-xs text-foreground/45">PDF up to 25 MB</span>
        </label>

        {uploadNote && (
          <p className="float-in mt-3 rounded-lg bg-emerald-500/10 px-3 py-2 text-sm text-emerald-300">
            ✅ {uploadNote}
          </p>
        )}
        {uploadError && (
          <p className="float-in mt-3 rounded-lg bg-red-500/10 px-3 py-2 text-sm text-red-300">
            ⚠️ {uploadError}
          </p>
        )}
      </section>

      {/* Chat */}
      <section className="glass flex flex-1 flex-col overflow-hidden rounded-2xl">
        <h2 className="flex items-center gap-2 border-b border-white/8 px-5 py-4 text-sm font-semibold text-foreground/80">
          <span className="grid h-6 w-6 place-items-center rounded-full bg-cyan-500/20 text-xs text-cyan-300">
            2
          </span>
          Ask a question
        </h2>

        <div className="scroll-slim flex-1 space-y-4 overflow-y-auto p-5">
          {messages.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center gap-2 py-12 text-center">
              <span className="text-3xl opacity-60">💬</span>
              <p className="text-sm text-foreground/40">
                {indexed > 0
                  ? "Ask anything about your uploaded documents."
                  : "Upload a PDF first, then ask away."}
              </p>
            </div>
          )}
          {messages.map((m, i) => (
            <Bubble key={i} role={m.role} text={m.text} />
          ))}
          {asking && <Thinking />}
          <div ref={chatEndRef} />
        </div>

        <form
          onSubmit={handleAsk}
          className="flex gap-2 border-t border-white/8 p-3"
        >
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="What is this document about?"
            className="flex-1 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm outline-none transition placeholder:text-foreground/35 focus:border-fuchsia-400/50 focus:bg-white/[0.05]"
          />
          <button
            type="submit"
            disabled={asking || !question.trim()}
            className="rounded-xl bg-gradient-to-r from-violet-500 to-fuchsia-500 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-fuchsia-500/25 transition hover:shadow-fuchsia-500/40 hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
          >
            Ask
          </button>
        </form>
      </section>

      <footer className="pt-1 text-center text-xs text-foreground/30">
        Answers are grounded strictly in your uploaded PDFs.
      </footer>
    </main>
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
      className={`inline-flex shrink-0 items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium ${
        ok
          ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
          : "border-red-500/30 bg-red-500/10 text-red-300"
      }`}
      title={error ?? undefined}
    >
      <span className="relative flex h-2 w-2">
        {ok && (
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
        )}
        <span
          className={`relative inline-flex h-2 w-2 rounded-full ${
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
    <span className="inline-flex items-center gap-1.5 rounded-full border border-white/8 bg-white/[0.04] px-3 py-1 text-foreground/65">
      <span>{icon}</span>
      {children}
    </span>
  );
}

function Bubble({
  role,
  text,
}: {
  role: "user" | "assistant";
  text: string;
}) {
  const isUser = role === "user";
  return (
    <div className={`float-in flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
          isUser
            ? "rounded-br-sm bg-gradient-to-br from-violet-500 to-fuchsia-500 text-white shadow-lg shadow-fuchsia-500/20"
            : "rounded-bl-sm border border-white/8 bg-white/[0.05] text-foreground/90"
        }`}
      >
        {text}
      </div>
    </div>
  );
}

function Thinking() {
  return (
    <div className="float-in flex justify-start">
      <div className="flex items-center gap-1.5 rounded-2xl rounded-bl-sm border border-white/8 bg-white/[0.05] px-4 py-3">
        <span className="dot h-2 w-2 rounded-full bg-fuchsia-300" />
        <span
          className="dot h-2 w-2 rounded-full bg-fuchsia-300"
          style={{ animationDelay: "0.2s" }}
        />
        <span
          className="dot h-2 w-2 rounded-full bg-fuchsia-300"
          style={{ animationDelay: "0.4s" }}
        />
      </div>
    </div>
  );
}
