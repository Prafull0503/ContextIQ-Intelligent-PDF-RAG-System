# ContextIQ

A production-ready **Retrieval-Augmented Generation** service. Upload PDF
documents, and the system extracts → cleans → chunks → embeds the text, stores
the vectors in a **persistent ChromaDB**, and answers questions **grounded only
in the uploaded content** using an LLM (OpenAI **or** Google Gemini — selectable
via environment variables, no code changes).

---

## ✨ Features

- **PDF ingestion pipeline** — load, clean, chunk (`RecursiveCharacterTextSplitter`), embed, persist.
- **Pluggable providers** — OpenAI / Gemini / Ollama for the LLM; OpenAI / Gemini / HuggingFace / Ollama for embeddings.
- **Persistent vector store** — ChromaDB on local disk; survives restarts.
- **Grounded answers** — the model is instructed to answer *only* from retrieved context.
- **Source tracking** — every answer returns the source chunks (filename + page + similarity score).
- **Confidence score** — derived from retrieval similarity.
- **Multiple PDFs** — ingest as many as you like into one collection.
- **Async FastAPI** — blocking work offloaded to a thread pool.
- **Robust error handling** — invalid/empty PDFs, missing API keys, vector-DB and LLM failures → proper HTTP status codes.
- **Structured logging** — across upload, chunking, embedding, retrieval and generation.
- **Typed & modular** — Pydantic models, type hints, SOLID service layer, tests.

---

## 🏗️ Architecture

```
                         ┌──────────────────────────────────────────┐
                         │                FastAPI                    │
                         │   /upload-pdf      /ask       /health      │
                         └───────┬───────────────┬───────────────────┘
                                 │               │
                  ┌──────────────▼──┐        ┌───▼───────────────┐
   INGEST (write) │ IngestionPipeline│  ASK  │   RAGPipeline      │ (read)
                  └──────────────┬──┘        └───┬───────────────┘
   load PDF                      │               │  embed question
   clean text                   │               │  similarity search (top-K)
   chunk (overlap)              │               │  inject context → LLM
   embed                        │               │  grounded answer + sources
        │                       │               │        │
        ▼                       ▼               ▼         ▼
  ┌───────────┐         ┌────────────────────────┐   ┌─────────┐
  │ Embeddings│◄────────┤      ChromaDB           │   │   LLM   │
  │ OpenAI /  │         │  (persistent on disk)   │   │ OpenAI /│
  │ HuggingFace│        └────────────────────────┘   │ Gemini  │
  └───────────┘                                       └─────────┘
```

### Project structure

```
ContextIQ/
├── app/
│   ├── api/              # FastAPI routers
│   │   └── routes.py
│   ├── application.py    # App factory: lifespan, CORS, exception handlers
│   ├── core/             # Config (pydantic-settings) + logging
│   │   ├── config.py
│   │   └── logging_config.py
│   ├── models/           # Pydantic request/response schemas
│   │   └── schemas.py
│   ├── rag/              # RAG pipelines
│   │   ├── ingestion.py  # write path: load→clean→chunk→embed→store
│   │   └── pipeline.py   # read path: retrieve→inject→generate
│   ├── services/         # Reusable services / composition root
│   │   ├── embedding_service.py
│   │   ├── llm_service.py
│   │   ├── vectorstore_service.py
│   │   └── rag_service.py
│   └── utils/            # Text cleaning + domain exceptions
│       ├── exceptions.py
│       └── text_cleaning.py
├── data/
│   ├── pdfs/             # Uploaded PDFs
│   └── chroma_db/        # Persistent vector store
├── tests/
├── .env / .env.example
├── requirements.txt
├── main.py
└── README.md
```

---

## 🚀 Setup

> Requires **Python 3.13+**.

### 1. Create & activate a virtual environment

```bash
# macOS / Linux
python3 -m venv venv
source venv/bin/activate

# Windows (PowerShell)
python -m venv venv
venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

The defaults run **fully locally via Ollama** — no API key required. Install
[Ollama](https://ollama.com), then pull the models:

```bash
ollama serve                  # start the local server
ollama pull llama3.1          # LLM
ollama pull nomic-embed-text  # embeddings
```

To use a cloud provider instead, set `LLM_PROVIDER=openai` + `OPENAI_API_KEY`
(or `LLM_PROVIDER=gemini` + `GOOGLE_API_KEY`) in `.env`.

### 4. Run the server

```bash
uvicorn main:app --reload
```

Open the interactive docs at **http://localhost:8000/docs**.

---

## ⚙️ Environment variables

| Variable | Description | Example |
|---|---|---|
| `LLM_PROVIDER` | LLM backend: `openai`, `gemini` or `ollama` | `ollama` |
| `EMBEDDING_PROVIDER` | Embeddings backend: `openai`, `gemini`, `huggingface` or `ollama` | `gemini` |
| `OPENAI_API_KEY` | OpenAI key (only if using OpenAI) | `sk-...` |
| `GOOGLE_API_KEY` | Google key (only if using Gemini) | `AIza...` |
| `OLLAMA_BASE_URL` | Ollama server URL (only if using Ollama) | `http://localhost:11434` |
| `LLM_MODEL` | Chat model name | `llama3.1` / `gpt-4o-mini` / `gemini-flash-latest` |
| `EMBEDDING_MODEL` | Embedding model name | `nomic-embed-text` / `text-embedding-3-small` |
| `CHROMA_DB_PATH` | Persistent vector-store dir | `./data/chroma_db` |
| `CHROMA_COLLECTION_NAME` | Collection name | `rag_documents` |
| `CHUNK_SIZE` | Characters per chunk | `1000` |
| `CHUNK_OVERLAP` | Overlap between chunks | `150` |
| `PDF_UPLOAD_DIR` | Where uploads are stored | `./data/pdfs` |
| `RETRIEVAL_TOP_K` | Chunks retrieved per query | `5` |
| `LLM_TEMPERATURE` | Generation temperature | `0.0` |
| `LLM_MAX_TOKENS` | Max output tokens | `1024` |
| `LOG_LEVEL` | Logging level | `INFO` |

---

## 📡 API usage

### `GET /health`

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "healthy",
  "llm_provider": "openai",
  "embedding_provider": "huggingface",
  "documents_indexed": 42
}
```

### `POST /upload-pdf`

```bash
curl -X POST http://localhost:8000/upload-pdf \
  -F "file=@/path/to/document.pdf"
```

```json
{
  "message": "PDF processed successfully",
  "filename": "document.pdf",
  "chunks_created": 18,
  "pages": 12
}
```

### `POST /ask`

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is this document about?"}'
```

```json
{
  "answer": "The document describes ...",
  "sources": [
    {
      "content": "…retrieved chunk text…",
      "source": "document.pdf",
      "page": 3,
      "score": 0.83
    }
  ],
  "confidence": 0.81
}
```

You may override retrieval depth per request:

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Summarise section 2", "top_k": 8}'
```

---

## 🧪 Tests

```bash
pytest -q
```

The API tests override the service with a fake, so they run fast and need no
API keys or model downloads.

---

## 🛠️ Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| `OPENAI_API_KEY is required ...` (HTTP 500) | Set the key in `.env`, or switch `LLM_PROVIDER`/`EMBEDDING_PROVIDER`. |
| `409 No documents have been indexed yet` | Upload a PDF via `/upload-pdf` before asking. |
| `422 ... no extractable text` | The PDF is image-only/scanned — it needs OCR before ingestion. |
| `400 Only .pdf files are accepted` | Upload a valid `.pdf`. |
| First startup is slow | HuggingFace downloads the embedding model once, then caches it. |
| `Connection refused` to `localhost:11434` | Ollama isn't running — start it with `ollama serve`. |
| `model "..." not found` (Ollama) | Pull it first: `ollama pull llama3.1` and `ollama pull nomic-embed-text`. |
| `502 LLM failed to generate an answer` | Check API key validity, model name, and network/quota. |
| Answers ignore my new PDF | Confirm `/upload-pdf` returned `201` and `documents_indexed` increased on `/health`. |
| Want a clean index | Stop the server and delete the `data/chroma_db/` directory. |

---

## 🔁 Switching providers (no code changes)

**Gemini-only (single API key for both LLM and embeddings — no local models):**

```env
LLM_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini
GOOGLE_API_KEY=AIza...
LLM_MODEL=gemini-flash-latest
EMBEDDING_MODEL=models/gemini-embedding-001
```

**Fully local with Ollama (no API key):**

```bash
# 1. Install Ollama from https://ollama.com, then:
ollama serve
ollama pull llama3.1          # the LLM
ollama pull nomic-embed-text  # the embedding model
```

```env
LLM_PROVIDER=ollama
EMBEDDING_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL=llama3.1
EMBEDDING_MODEL=nomic-embed-text
```

**Use Gemini for generation, HuggingFace for embeddings (no OpenAI key):**

```env
LLM_PROVIDER=gemini
EMBEDDING_PROVIDER=huggingface
GOOGLE_API_KEY=AIza...
LLM_MODEL=gemini-flash-latest
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

**All-OpenAI:**

```env
LLM_PROVIDER=openai
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
EMBEDDING_MODEL=text-embedding-3-small
```

> **Note:** embeddings define the vector space. If you change
> `EMBEDDING_PROVIDER`/`EMBEDDING_MODEL` after ingesting, delete
> `data/chroma_db/` and re-upload your PDFs so the index is rebuilt
> consistently.
